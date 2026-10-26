// Поведение страниц внутри модального окна. Внутри iframe «Закрыть» и «Отмена» закрывают окно,
// а остальные ссылки вида "../" открываются в основной странице.
(function () {
    const inFrame = window.parent !== window;

    document.addEventListener('click', function (event) {
        const link = event.target.closest('a[href]');
        if (!link || !inFrame) return;

        const href = link.getAttribute('href');
        if (!/^\.\.\//.test(href)) return;

        event.preventDefault();
        const closesWindow = link.classList.contains('popup-close') || link.classList.contains('button-secondary');
        const message = closesWindow
            ? { type: 'popup-close' }
            : { type: 'popup-navigate', url: new URL(href, location.href).href };
        parent.postMessage(message, location.origin);
    });

    // Esc, нажатый внутри iframe, не доходит до <dialog> родителя, поэтому пересылаем его сами.
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && inFrame) parent.postMessage({ type: 'popup-close' }, location.origin);
    });
})();
