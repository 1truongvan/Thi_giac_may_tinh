'use strict';

const navigationToggle = document.querySelector('.nav-toggle');
const navigation = document.querySelector('#main-navigation');
if (navigationToggle && navigation) {
    navigationToggle.addEventListener('click', () => {
        const expanded = navigationToggle.getAttribute('aria-expanded') !== 'true';
        navigationToggle.setAttribute('aria-expanded', String(expanded));
        navigation.classList.toggle('is-open', expanded);
    });
    navigation.addEventListener('click', (event) => {
        if (event.target.closest('a')) {
            navigationToggle.setAttribute('aria-expanded', 'false');
            navigation.classList.remove('is-open');
        }
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            navigationToggle.setAttribute('aria-expanded', 'false');
            navigation.classList.remove('is-open');
        }
    });
}
