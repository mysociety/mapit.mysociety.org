analytics = {

    trackEvents: function(listOfEvents){
        // Takes a list of arguments suitable for trackEvent.
        // Returns a jQuery Deferred object.
        // The deferred object is resolved when
        // all of the trackEvent calls are resolved.
        var dfd = $.Deferred();
        var deferreds = [];
        var _this = this;
        $.each(listOfEvents, function(i, params) {
                deferreds.push(_this.trackEvent(params));
        });
        $.when.apply($, deferreds).done(function() {
                dfd.resolve();
        });
        return dfd.promise();
    },

    trackEvent: function(params){
        // Takes an object of event parameters, eg:
        // { eventCategory: 'foo', eventAction: 'bar' }
        // Returns a jQuery Deferred object.
        // The deferred object is resolved when the GA call
        // completes or fails to respond within 2 seconds.
        var dfd = $.Deferred();

        if (typeof ga === 'undefined' || !ga.loaded) {
            // GA has not loaded (blocked by adblock?)
            return dfd.resolve();
        }

        var defaults = {
            hitType: 'event',
            eventLabel: document.title,
            hitCallback: function(){
                dfd.resolve();
            }
        }

        ga('send', $.extend(defaults, params));

        // Wait a maximum of 2 seconds for GA response.
        setTimeout(function(){
            dfd.resolve();
        }, 2000);

        return dfd.promise();
    },

    trackLinkClick: function(e, params){
        // A shortcut for the most common event tracking use-case:
        // tracking clicks on a link that would normally lead to
        // a new page, and waiting until the event has been tracked
        // before continuing to the new page.
        e.preventDefault();
        var _this = this;
        var href = $(e.currentTarget).attr('href');
        var defaults = {
            eventAction: e.type
        }

        _this.trackEvent(
            $.extend(defaults, params)
        ).done(function() {
            if (href) {
                window.location.href = href;
            }
        });
    }
}

$(function(){

    $(document).on('submit', '.homepage-try', function(e) {
        analytics.trackEvent({
            eventCategory: 'homepage-try__search',
            eventAction: e.type
        });
    });

    $(document).on('click', '.homepage-try-result__close', function(e) {
        analytics.trackEvent({
            eventCategory: 'homepage-try__close',
            eventAction: e.type
        });
    });

    $(document).on('click', '.homepage-try-result__area', function(e) {
        analytics.trackEvent({
            eventCategory: 'homepage-try__area-box',
            eventAction: e.type
        });
    });

    $(document).on('click', '.homepage-try-result h2 a', function(e){
        analytics.trackLinkClick(e, {
            eventCategory: 'homepage-try__heading-postcode-link'
        });
    });

    $(document).on('click', '.homepage-try-result__open', function(e){
        analytics.trackLinkClick(e, {
            eventCategory: 'homepage-try__show-full-results'
        });
    });

    $('.pricing__option .btn--primary').on('click', function(e){
        analytics.trackLinkClick(e, {
            eventCategory: 'pricing__sign-up-button'
        });
    });

    $('.pricing__option .btn[href="/docs/"]').on('click', function(e){
        analytics.trackLinkClick(e, {
            eventCategory: 'pricing__docs-button'
        });
    });
});
