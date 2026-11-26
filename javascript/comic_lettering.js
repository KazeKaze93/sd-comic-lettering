// Host side of Comic Lettering: opens the editor (a React page in an iframe) over the page
// and passes it the image the gallery shows. Host JS: no arrow functions, no template literals.
(function () {
    var overlay = null;
    var frame = null;
    var ready = false;
    var tab = 'txt2img';

    function app() {
        return (typeof gradioApp === 'function') ? gradioApp() : document;
    }

    // The image the gallery shows now, and where it stands among the gallery's images.
    function galleryImage() {
        var gallery = app().querySelector('#' + tab + '_gallery');
        // The gallery lists its images twice while one is open: as a grid and as a strip
        // under the open image. Count one of the two.
        var thumbs = gallery ? gallery.querySelectorAll('.grid-wrap .thumbnail-item img') : [];
        if (gallery && !thumbs.length) {
            thumbs = gallery.querySelectorAll('.thumbnails .thumbnail-item img');
        }
        var index = 0;
        if (typeof selected_gallery_index === 'function') {
            index = selected_gallery_index();
        }
        if (index < 0) {
            index = 0;
        }
        var shown = gallery ? gallery.querySelector('.preview > img, img[data-testid="detailed-image"]') : null;
        var picked = shown || thumbs[index] || (gallery ? gallery.querySelector('img') : null);
        var url = picked && picked.src && picked.src.indexOf('data:') !== 0 ? picked.src : null;
        return {tab: tab, url: url, index: index, count: thumbs.length || (url ? 1 : 0)};
    }

    function theme() {
        var dark = document.body.classList.contains('dark') || app().querySelector('.dark') !== null;
        return dark ? 'dark' : 'light';
    }

    function send() {
        if (!frame || !ready || !frame.contentWindow) {
            return;
        }
        frame.contentWindow.postMessage({type: 'SDCL_INIT', image: galleryImage(), theme: theme()},
            window.location.origin);
    }

    function close() {
        if (overlay) {
            overlay.style.display = 'none';
        }
    }

    function build() {
        overlay = document.createElement('div');
        overlay.id = 'comic_lettering_overlay';
        overlay.style.cssText = 'position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,0.6);display:none;';
        frame = document.createElement('iframe');
        frame.title = 'Comic Lettering';
        frame.src = '/comic_lettering/ui';
        frame.style.cssText = 'position:absolute;inset:12px;width:calc(100% - 24px);height:calc(100% - 24px);' +
            'border:1px solid rgba(128,128,128,0.4);border-radius:8px;background:#111317;';
        overlay.appendChild(frame);
        document.body.appendChild(overlay);
    }

    window.addEventListener('message', function (event) {
        if (!frame || event.source !== frame.contentWindow || event.origin !== window.location.origin) {
            return;
        }
        var data = event.data || {};
        if (data.type === 'SDCL_READY') {
            ready = true;
            send();
        } else if (data.type === 'SDCL_CLOSE') {
            close();
        } else if (data.type === 'SDCL_TO_GALLERY' && typeof data.session === 'string') {
            // The hidden Gradio button reads the session id from here and fills the gallery.
            window.sdclSession = data.session;
            var button = app().querySelector('#comic_lettering_to_gallery');
            if (button) {
                button.click();
            }
            close();
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && overlay && overlay.style.display !== 'none') {
            close();
        }
    });

    window.sdclOpen = function (which) {
        tab = which || 'txt2img';
        if (!overlay) {
            build();
        }
        overlay.style.display = 'block';
        send();  // the page itself asks again with SDCL_READY once it has loaded
    };
})();
