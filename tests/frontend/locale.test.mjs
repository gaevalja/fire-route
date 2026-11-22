import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import test from 'node:test';

const script = readFileSync(new URL('../../frontend/scenario/locale.js', import.meta.url), 'utf8');

function loadLocale(saved) {
  const events = {};
  const settings = new Map(saved ? [['fr-locale', saved]] : []);
  const browser = {
    localStorage: {getItem: key => settings.get(key), setItem: (key,value) => settings.set(key,value)},
    addEventListener: (event, listener) => { events[event] = listener; },
  };
  runInNewContext(script, browser);
  return {locale: browser.FireRouteLocale, settings, events};
}

test('language is persisted and synchronized without redundant redraws', () => {
  const {locale, settings, events} = loadLocale('en');
  const seen = [];
  locale.onChange(() => seen.push(locale.getLanguage()));
  assert.equal(locale.t('기록', 'Recording'), 'Recording');
  locale.setLanguage('invalid');
  locale.setLanguage('en');
  assert.deepEqual(seen, []);
  locale.setLanguage('ko');
  assert.equal(settings.get('fr-locale'), 'ko');
  events.storage({key: 'other', newValue: 'en'});
  events.storage({key: 'fr-locale', newValue: 'en'});
  assert.deepEqual(seen, ['ko', 'en']);
});

test('localized text and accessibility labels round trip', () => {
  const {locale} = loadLocale();
  const attributes = new Map([['aria-label', '재생 위치'], ['data-en-aria-label', 'Playback position'], ['data-en', 'Playback']]);
  const element = {textContent: '재생', getAttribute: key => attributes.get(key), setAttribute: (key,value) => attributes.set(key,value)};
  const document = {documentElement: {}, querySelectorAll: selector => attributes.has(selector.slice(1,-1)) ? [element] : []};
  locale.localize(document);
  assert.equal(document.documentElement.lang, 'ko');
  locale.setLanguage('en');
  locale.localize(document);
  assert.equal(element.textContent, 'Playback');
  assert.equal(attributes.get('aria-label'), 'Playback position');
  locale.setLanguage('ko');
  locale.localize(document);
  assert.equal(element.textContent, '재생');
  assert.equal(attributes.get('aria-label'), '재생 위치');
});
