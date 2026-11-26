// Small helpers for the Comic Lettering panel. Host JS: no arrow functions, no template literals.
(function () {
    // --- 1. A click on an open list's field closes the list. -------------------------
    // A Gradio 3 dropdown stays open when its field is clicked a second time: the click
    // only re-selects the text.
    var closedAt = 0;

    function openField(target) {
        if (!target || !target.closest) {
            return null;
        }
        if (!target.closest('[id^="comic_lettering_"]') || target.closest('ul.options')) {
            return null;
        }
        var wrap = target.closest('.wrap-inner');
        if (!wrap || !wrap.classList.contains('showOptions')) {
            return null;
        }
        return wrap.querySelector('input');
    }

    document.addEventListener('mousedown', function (event) {
        var input = openField(event.target);
        if (!input) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        input.blur();
        closedAt = Date.now();
    }, true);

    // The click that follows that mousedown would open the list again.
    document.addEventListener('click', function (event) {
        if (Date.now() - closedAt > 400) {
            return;
        }
        if (event.target && event.target.closest && event.target.closest('[id^="comic_lettering_"] .wrap-inner')) {
            event.preventDefault();
            event.stopPropagation();
            closedAt = 0;
        }
    }, true);

    // --- 2. Mark buttons insert at the cursor of the text field used last. ------------
    var lastField = {};  // panel id -> textarea

    function panelOf(node) {
        var box = node && node.closest ? node.closest('[id^="comic_lettering_"]') : null;
        while (box && !/^comic_lettering_(txt2img|img2img)$/.test(box.id)) {
            box = box.parentElement ? box.parentElement.closest('[id^="comic_lettering_"]') : null;
        }
        return box;
    }

    document.addEventListener('focusin', function (event) {
        var target = event.target;
        if (!target || target.tagName !== 'TEXTAREA') {
            return;
        }
        var panel = panelOf(target);
        if (panel) {
            lastField[panel.id] = target;
        }
    }, true);

    window.sdclInsert = function (panelId, mark) {
        var app = (typeof gradioApp === 'function') ? gradioApp() : document;
        var field = lastField[panelId];
        if (!field || !field.isConnected) {
            field = app.querySelector('#' + panelId + '_sfx textarea');
        }
        if (!field) {
            return;
        }
        var start = field.selectionStart === null ? field.value.length : field.selectionStart;
        var end = field.selectionEnd === null ? start : field.selectionEnd;
        var before = field.value.slice(0, start);
        var after = field.value.slice(end);
        // Keep marks apart from the neighbouring word, as typed text would be.
        var lead = (before && !/\s$/.test(before)) ? ' ' : '';
        var text = lead + mark;
        var setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
        setter.call(field, before + text + after);
        field.dispatchEvent(new Event('input', {bubbles: true}));
        field.focus();
        field.selectionStart = field.selectionEnd = before.length + text.length;
    };
})();
