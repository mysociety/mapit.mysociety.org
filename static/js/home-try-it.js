var renderTemplate = function renderTemplate(templateName, data) {
    data = data || {};
    var source = $('#' + templateName);
    if(source.length){
        return _.template( source.html() )(data);
    } else {
        throw 'renderTemplate Error: Could not find source template with matching #' + templateName;
    }
}

$(function() {
    L.Icon.Default.prototype.options.imagePath = '/static/mapit/leaflet/images/';

    $('.homepage-try').on('submit', function(e) {
        e.preventDefault();

        var $try = $(this);
        var pc = $try.find('[name="pc"]').val();

        var fallback = function fallback() {
            window.location = '/postcode/' + encodeURIComponent(pc) + '.html';
        }

        var displayError = function displayError(error) {
            $(renderTemplate('try-error', { error: error })).insertAfter($try);
        }

        var extractAreas = function extractAreas(areas) {
            newAreas = [];
            var areasToIgnore = [
                'EUP', // is always just "European Parliament"
                'OMG', // nobody cares about Middle layer output areas
                'OMF', // nobody cares about Middle layer output areas
                'OLG', // we want "full" LSOAs, not "generalised" LSOAs
                'COI', // is always just "Isles of Scilly"
                'GLA', // is always just "Greater London Authority"
                'LAE', // is always just "London Assembly"
                'LAS', // is always just "London Assembly"
                'WMP' // is always just "House of Commons"
            ];

            _.each(areas, function(area) {
                if (areasToIgnore.indexOf(area.type) > -1) {
                    return true;
                }

                if( ['OLF'].indexOf(area.type) > -1 ) {
                    var type_name = area.type_name.replace(' (Full)', '');
                } else {
                    var type_name = area.type_name;
                }

                newAreas.push({
                    name: area.name,
                    type: area.type,
                    type_name: type_name,
                    id: area.id
                });
            });

            return newAreas;
        }

        var displayPostcode = function displayPostcode(data) {
            var context = {
                postcode: data.postcode,
                areas: extractAreas(data.areas)
            };

            $(renderTemplate('try-result', context)).insertAfter($try);

            var map = new L.Map("homepage-leaflet", {
                scrollWheelZoom: false
            });
            map.attributionControl.setPrefix('');

            var point = new L.LatLng(data.wgs84_lat, data.wgs84_lon);
            map.setView(point, 14);

            var layers = {
                osm: new L.TileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                    attribution: 'Map © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
                    maxZoom: 14,
                    minZoom: 4
                }),
                marker: new L.Marker(point)
            };
            map.addLayer(layers.marker);
            map.addLayer(layers.osm);

            // Find a smallish area, and pre-select it.
            var lsoa = _.findWhere(context.areas, {type: 'OLF'});
            if (lsoa) {
                addArea(map, layers, lsoa.id);
                $('[data-areaid="' + lsoa.id + '"]').addClass('selected');
            }

            $('.homepage-try-result__area').on('click', function(e){
                e.preventDefault();

                var id = $(this).data('areaid');

                if (id in layers) {
                    removeArea(map, layers, id);
                    $(this).removeClass('selected');
                } else {
                    $(this).siblings('.selected').each(function(){
                        removeArea(map, layers, $(this).data('areaid'));
                        $(this).removeClass('selected');
                    });
                    addArea(map, layers, id);
                    $(this).addClass('selected');
                }
            });

            $('.homepage-try-result__close').on('click', function(){
                $('.homepage-try-result').slideUp(250);
                $('.homepage-try form input[type="text"]').val('');
            });
        }

        var removeArea = function removeArea(map, layers, area_id){
            if (area_id in layers) {
                map.removeLayer( layers[area_id] );
                delete layers[area_id];
            }
        }

        var addArea = function addArea(map, layers, area_id){
            $.ajax({
                dataType: 'json',
                url: '/area/' + area_id + '.geojson',
                data: {
                    simplify_tolerance: '0.0001'
                }

            }).done(function(geojson){
                layers[area_id] = new L.GeoJSON(geojson, {
                    style: {
                        color: '#4FADED',
                        weight: 3,
                        opacity: 1
                    }
                });
                map.addLayer(layers[area_id]);
                map.fitBounds(layers[area_id].getBounds());

            }).fail(function(){
                // This might happen if the area has no polygons.
                // (We try to exclude these using areasToIgnore, but some
                // might slip through.) Seems silly to feed back the error
                // to the user, so just deselect the button and move on.
                $('[data-areaid="' + area_id + '"]').removeClass('selected');

            });
        }

        // Clear out any existing results elements
        $('.homepage-try-result, .homepage-try-error, .homepage-try-loading').remove();

        $(renderTemplate('try-loading')).insertAfter($try);

        $("html, body").animate({
            scrollTop: $(this).offset().top
        }, 500);

        $.ajax({
            dataType: "json",
            url: '/postcode/' + encodeURIComponent(pc)

        }).always(function() {
            $('.homepage-try-loading').remove();

        }).done(function(data) {
            if (data.areas && ! $.isEmptyObject(data.areas)) {
                displayPostcode(data);
            } else {
                fallback();
            }

        }).fail(function(jqXHR) {
            if (jqXHR.status == 404 && jqXHR.responseJSON) {
                displayError(jqXHR.responseJSON.error);
            } else {
                fallback();
            }
        });
    });
});
