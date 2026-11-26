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
            var button = app().querySelector('#comic_lettering_to_gallery_' + tab);
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

    // An icon in the row of tools under Generate, next to Style Grid's when that is installed.
    var NS = 'http://www.w3.org/2000/svg';

    function icon() {
        var svg = document.createElementNS(NS, 'svg');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('fill', 'none');
        svg.setAttribute('stroke', 'currentColor');
        svg.setAttribute('stroke-width', '1.8');
        svg.setAttribute('stroke-linecap', 'round');
        svg.setAttribute('stroke-linejoin', 'round');
        svg.setAttribute('aria-hidden', 'true');
        // A speech bubble with a letter in it.
        var parts = ['M4 4h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1h-8l-4.5 4v-4H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z',
            'M9.3 13l2.7-6.2 2.7 6.2', 'M10.3 10.9h3.4'];
        for (var i = 0; i < parts.length; i++) {
            var path = document.createElementNS(NS, 'path');
            path.setAttribute('d', parts[i]);
            svg.appendChild(path);
        }
        return svg;
    }

    function toolButton(which) {
        var button = document.createElement('button');
        button.type = 'button';
        button.id = 'comic_lettering_tool_' + which;
        button.className = 'sdcl-tool-btn lg secondary gradio-button tool';
        button.title = 'Open Comic Lettering';
        button.setAttribute('aria-label', 'Open Comic Lettering');
        button.appendChild(icon());
        button.addEventListener('click', function (event) {
            event.preventDefault();
            event.stopPropagation();
            window.sdclOpen(which);
        });
        return button;
    }

    // Returns true once the icon stands where it should.
    function placeTool(which) {
        var root = app();
        var tools = root.querySelector('#' + which + '_tools');
        if (!tools) {
            return false;
        }
        var row = tools.querySelector(':scope > div.form, :scope > div[style*="flex"]') || tools;
        var button = root.querySelector('#comic_lettering_tool_' + which) || toolButton(which);
        var neighbour = root.querySelector('#sg_trigger_' + which);
        if (neighbour && neighbour.parentNode) {
            if (neighbour.nextSibling !== button) {
                neighbour.parentNode.insertBefore(button, neighbour.nextSibling);
            }
        } else if (button.parentNode !== row) {
            row.appendChild(button);
        }
        return true;
    }

    // The tools row appears some time after the page script runs, and Style Grid adds its
    // button later still: look for a while, then stop.
    var tries = 0;
    var timer = setInterval(function () {
        tries += 1;
        placeTool('txt2img');
        placeTool('img2img');
        if (tries > 120) {
            clearInterval(timer);
        }
    }, 500);
})();
