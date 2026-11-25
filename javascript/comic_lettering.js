// A Gradio 3 dropdown stays open when its field is clicked a second time: the click
// only re-selects the text. In the Comic Lettering panel a click on an open list's
// field closes the list instead.
(function () {
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
})();
