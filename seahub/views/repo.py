# -*- coding: utf-8 -*-
import logging
import urllib
import base64
import simplejson as json

from django.core.urlresolvers import reverse
from django.contrib.sites.models import RequestSite
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.template.loader import render_to_string

import seaserv
from seaserv import seafile_api

from seahub.auth.decorators import login_required
from seahub.avatar.templatetags.avatar_tags import avatar
from seahub.avatar.templatetags.group_avatar_tags import grp_avatar
from seahub.contacts.models import Contact
from seahub.forms import RepoPassowrdForm
from seahub.options.models import UserOptions, CryptoOptionNotSetError
from seahub.share.models import FileShare, UploadLinkShare
from seahub.views import gen_path_link, get_repo_dirents, \
    check_repo_access_permission

from seahub.utils import get_ccnetapplet_root, gen_file_upload_url, \
    get_httpserver_root, gen_dir_share_link, gen_shared_upload_link, \
    get_max_upload_file_size, new_merge_with_no_conflict, \
    get_commit_before_new_merge
from seahub.settings import ENABLE_SUB_LIBRARY, FORCE_SERVER_CRYPTO

# Get an instance of a logger
logger = logging.getLogger(__name__)

def get_repo(repo_id):
    return seafile_api.get_repo(repo_id)

def get_commit(repo_id, repo_version, commit_id):
    return seaserv.get_commit(repo_id, repo_version, commit_id)

def get_repo_size(repo_id):
    return seafile_api.get_repo_size(repo_id)

def is_password_set(repo_id, username):
    return seafile_api.is_password_set(repo_id, username)

# def check_dir_access_permission(username, repo_id, path):
#     """Check user has permission to view the directory.
#     1. check whether this directory is private shared.
#     2. if failed, check whether the parent of this directory is private shared.
#     """
     
#     pfs = PrivateFileDirShare.objects.get_private_share_in_dir(username,
#                                                                repo_id, path)
#     if pfs is None:
#         dirs = PrivateFileDirShare.objects.list_private_share_in_dirs_by_user_and_repo(username, repo_id)
#         for e in dirs:
#             if path.startswith(e.path):
#                 return e.permission
#         return None
#     else:
#         return pfs.permission

def get_path_from_request(request):
    path = request.GET.get('p', '/')
    if path[-1] != '/':
        path = path + '/'
    return path

def get_next_url_from_request(request):
    return request.GET.get('next', None)

def get_nav_path(path, repo_name):
    return gen_path_link(path, repo_name)

def get_shared_groups_by_repo_and_user(repo_id, username):
    """Get all groups which this repo is shared.
    """
    repo_shared_groups = seaserv.get_shared_groups_by_repo(repo_id)

    # Filter out groups that user is joined.
    groups = [ x for x in repo_shared_groups if \
                   seaserv.is_group_user(x.id, username)]
    return groups

def is_no_quota(repo_id):
    return True if seaserv.check_quota(repo_id) < 0 else False

def get_upload_url(request, repo_id):
    username = request.user.username
    if check_repo_access_permission(repo_id, request.user) == 'rw':
        token = seafile_api.get_httpserver_access_token(repo_id, 'dummy',
                                                        'upload', username)
        return gen_file_upload_url(token, 'upload')
    else:
        return ''

# def get_api_upload_url(request, repo_id):
#     """Get file upload url for web api.
#     """
#     username = request.user.username
#     if check_repo_access_permission(repo_id, request.user) == 'rw':
#         token = seafile_api.get_httpserver_access_token(repo_id, 'dummy',
#                                                         'upload', username)
#         return gen_file_upload_url(token, 'upload-api')
#     else:
#         return ''

# def get_api_update_url(request, repo_id):
#     username = request.user.username
#     if check_repo_access_permission(repo_id, request.user) == 'rw':
#         token = seafile_api.get_httpserver_access_token(repo_id, 'dummy',
#                                                         'update', username)
#         return gen_file_upload_url(token, 'update-api')
#     else:
#         return ''

def get_fileshare(repo_id, username, path):
    if path == '/':    # no shared link for root dir
        return None
        
    l = FileShare.objects.filter(repo_id=repo_id).filter(
        username=username).filter(path=path)
    return l[0] if len(l) > 0 else None

def get_dir_share_link(fileshare):
    # dir shared link
    if fileshare:
        dir_shared_link = gen_dir_share_link(fileshare.token)
    else:
        dir_shared_link = ''
    return dir_shared_link

def get_uploadlink(repo_id, username, path):
    if path == '/':    # no shared upload link for root dir
        return None

    l = UploadLinkShare.objects.filter(repo_id=repo_id).filter(
        username=username).filter(path=path)
    return l[0] if len(l) > 0 else None

def get_dir_shared_upload_link(uploadlink):
    # dir shared upload link
    if uploadlink:
        dir_shared_upload_link = gen_shared_upload_link(uploadlink.token)
    else:
        dir_shared_upload_link = ''
    return dir_shared_upload_link

def render_repo(request, repo):
    """Steps to show repo page:
    If user has permission to view repo
      If repo is encrypt and password is not set on server
        return decrypt repo page
      If repo is not encrypt or password is set on server
        Show repo direntries based on requested path
    If user does not have permission to view repo
      return permission deny page
    """
    username = request.user.username
    path = get_path_from_request(request)
    user_perm = check_repo_access_permission(repo.id, request.user)
    if user_perm is None:
        return render_to_response('repo_access_deny.html', {
                'repo': repo,
                }, context_instance=RequestContext(request))

    sub_lib_enabled = UserOptions.objects.is_sub_lib_enabled(username)

    server_crypto = False
    if repo.encrypted:
        try:
            server_crypto = UserOptions.objects.is_server_crypto(username)
        except CryptoOptionNotSetError:
            return render_to_response('options/set_user_options.html', {
                    }, context_instance=RequestContext(request))
            
        if (repo.enc_version == 1 or (repo.enc_version == 2 and server_crypto)) \
                and not is_password_set(repo.id, username):
            return render_to_response('decrypt_repo_form.html', {
                    'repo': repo,
                    'next': get_next_url_from_request(request) or \
                        reverse('repo', args=[repo.id]),
                    'force_server_crypto': FORCE_SERVER_CRYPTO,
                    }, context_instance=RequestContext(request))

    # query context args
    applet_root = get_ccnetapplet_root()
    httpserver_root = get_httpserver_root()
    max_upload_file_size = get_max_upload_file_size()

    protocol = request.is_secure() and 'https' or 'http'
    domain = RequestSite(request).domain

    contacts = Contact.objects.get_contacts_by_user(username)
    for c in contacts:
        c.avatar = avatar(c.contact_email, 16)

    for g in request.user.joined_groups:
        g.avatar = grp_avatar(g.id, 20)

    head_commit = get_commit(repo.id, repo.version, repo.head_cmmt_id)
    if not head_commit:
        raise Http404

    if new_merge_with_no_conflict(head_commit):
        info_commit = get_commit_before_new_merge(head_commit)
    else:
        info_commit = head_commit

    repo_size = get_repo_size(repo.id)
    no_quota = is_no_quota(repo.id)
    search_repo_id = None if repo.encrypted else repo.id
    repo_owner = seafile_api.get_repo_owner(repo.id)
    is_repo_owner = True if repo_owner == username else False
    if is_repo_owner and not repo.is_virtual:
        show_repo_settings = True
    else:
        show_repo_settings = False

    more_start = None
    file_list, dir_list, dirent_more = get_repo_dirents(request, repo, head_commit, path, offset=0, limit=100)
    if dirent_more:
        more_start = 100
    zipped = get_nav_path(path, repo.name)
    repo_groups = get_shared_groups_by_repo_and_user(repo.id, username)
    if len(repo_groups) > 1:
        repo_group_str = render_to_string("snippets/repo_group_list.html",
                                          {'groups': repo_groups})
    else:
        repo_group_str = ''
    upload_url = get_upload_url(request, repo.id)

    fileshare = get_fileshare(repo.id, username, path)
    dir_shared_link = get_dir_share_link(fileshare)
    uploadlink = get_uploadlink(repo.id, username, path)

    open_local_info = base64.encodestring(json.dumps({
        'repo_id': repo.id,
        'repo_name': repo.name,
        'path': path[1:]
    }).encode('UTF-8'))
    dir_shared_upload_link = get_dir_shared_upload_link(uploadlink)

    return render_to_response('repo.html', {
            'repo': repo,
            'user_perm': user_perm,
            'repo_owner': repo_owner,
            'is_repo_owner': is_repo_owner,
            'show_repo_settings': show_repo_settings,
            'current_commit': head_commit,
            'info_commit': info_commit,
            'password_set': True,
            'repo_size': repo_size,
            'dir_list': dir_list,
            'file_list': file_list,
            'dirent_more': dirent_more,
            'more_start': more_start,
            'path': path,
            'zipped': zipped,
            'applet_root': applet_root,
            'groups': repo_groups,
            'repo_group_str': repo_group_str,
            'no_quota': no_quota,
            'max_upload_file_size': max_upload_file_size,
            'upload_url': upload_url,
            'httpserver_root': httpserver_root,
            'protocol': protocol,
            'domain': domain,
            'contacts': contacts,
            'fileshare': fileshare,
            'dir_shared_link': dir_shared_link,
            'uploadlink': uploadlink,
            'dir_shared_upload_link': dir_shared_upload_link,
            'search_repo_id': search_repo_id,
            'ENABLE_SUB_LIBRARY': ENABLE_SUB_LIBRARY,
            'server_crypto': server_crypto,
            "sub_lib_enabled": sub_lib_enabled,
            'open_local_info': open_local_info,
            }, context_instance=RequestContext(request))
   
@login_required    
def repo(request, repo_id):
    """Show repo page and handle POST request to decrypt repo.
    """
    repo = get_repo(repo_id)

    if not repo:
        raise Http404
    
    if request.method == 'GET':
        return render_repo(request, repo)
    elif request.method == 'POST':
        form = RepoPassowrdForm(request.POST)
        next = get_next_url_from_request(request) or reverse('repo',
                                                             args=[repo_id])
        if form.is_valid():
            return HttpResponseRedirect(next)
        else:
            return render_to_response('decrypt_repo_form.html', {
                    'repo': repo,
                    'form': form,
                    'next': next,
                    'force_server_crypto': FORCE_SERVER_CRYPTO,      
                    }, context_instance=RequestContext(request))
    
@login_required
def repo_history_view(request, repo_id):
    """View repo in history.
    """
    repo = get_repo(repo_id)
    if not repo:
        raise Http404

    username = request.user.username
    path = get_path_from_request(request)
    user_perm = check_repo_access_permission(repo.id, request.user)
    if user_perm is None:
        return render_to_response('repo_access_deny.html', {
                'repo': repo,
                }, context_instance=RequestContext(request))

    try:
        server_crypto = UserOptions.objects.is_server_crypto(username)
    except CryptoOptionNotSetError:
        # Assume server_crypto is ``False`` if this option is not set.
        server_crypto = False   
    
    if repo.encrypted and \
        (repo.enc_version == 1 or (repo.enc_version == 2 and server_crypto)) \
        and not is_password_set(repo.id, username):
        return render_to_response('decrypt_repo_form.html', {
                'repo': repo,
                'next': get_next_url_from_request(request) or \
                    reverse('repo', args=[repo.id]),
                'force_server_crypto': FORCE_SERVER_CRYPTO,
                }, context_instance=RequestContext(request))
    
    commit_id = request.GET.get('commit_id', None)
    if commit_id is None:
        return HttpResponseRedirect(reverse('repo', args=[repo.id]))
    current_commit = get_commit(repo.id, repo.version, commit_id)
    if not current_commit:
        current_commit = get_commit(repo.id, repo.version, repo.head_cmmt_id)

    file_list, dir_list = get_repo_dirents(request, repo, current_commit, path)
    zipped = get_nav_path(path, repo.name)
    search_repo_id = None if repo.encrypted else repo.id

    return render_to_response('repo_history_view.html', {
            'repo': repo,
            'user_perm': user_perm,
            'current_commit': current_commit,
            'dir_list': dir_list,
            'file_list': file_list,
            'path': path,
            'zipped': zipped,
            'search_repo_id': search_repo_id,
            }, context_instance=RequestContext(request))
    
