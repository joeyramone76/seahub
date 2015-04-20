define([
    'jquery',
    'simplemodal',
    'underscore',
    'backbone',
    'common',
    'app/views/add-repo'
], function($, simplemodal, _, Backbone, Common, AddRepoView) {
    'use strict';

    var AddGroupRepoView = AddRepoView.extend({
        initialize: function(repos) {
            console.log('init create repo popup in group');
            AddRepoView.prototype.initialize.apply(this, arguments);
        },
        
        templateData: function() {
            return {
                showSharePerm: true
            };
        },

        newAttributes: function() {
            var baseAttrs = AddRepoView.prototype.newAttributes.apply(this);

            return _.extend(baseAttrs, {'permission': $('select[name=permission]', this.$el).val()});
        },

    });

    return AddGroupRepoView;
});
