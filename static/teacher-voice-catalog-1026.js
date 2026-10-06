/* Canonical teacher-facing Kokoro voice catalog.
 * Voice IDs/labels come from /api/media-audio/status -> voiceOptions.
 * Do not duplicate voice maps in feature modules.
 */
(function () {
  'use strict';

  const state = {
    defaultVoice: '',
    options: [],
    byId: new Map(),
  };

  function normalize(payload) {
    const source = Array.isArray(payload)
      ? payload
      : (Array.isArray(payload?.voiceOptions) ? payload.voiceOptions : []);
    const seen = new Set();
    const rows = [];
    source.forEach(item => {
      const row = typeof item === 'string' ? {id:item, label:''} : (item || {});
      const id = String(row.id || '').trim();
      const label = String(row.label || '').trim();
      if (!id || seen.has(id)) return;
      seen.add(id);
      rows.push({id, label: label || '中文語音'});
    });
    return rows;
  }

  function options() {
    return state.options.map(item => ({...item}));
  }

  function update(payload = {}) {
    const rows = normalize(payload);
    if (!rows.length) return false;
    state.options = rows;
    state.byId = new Map(rows.map(item => [item.id, item]));
    const requestedDefault = String(payload?.defaultVoice || '').trim();
    state.defaultVoice = state.byId.has(requestedDefault) ? requestedDefault : rows[0].id;
    window.dispatchEvent(new CustomEvent('teacher-voice-catalog-updated-1026', {
      detail: {defaultVoice: state.defaultVoice, options: options()},
    }));
    return true;
  }

  function label(value) {
    const id = String(value || '').trim();
    return state.byId.get(id)?.label || '中文語音';
  }

  window.TeacherVoiceCatalog1026 = Object.freeze({
    update,
    label,
    options,
    defaultVoice: () => state.defaultVoice,
  });

  if (window.TeacherMediaAudioStatus1014) update(window.TeacherMediaAudioStatus1014);
  window.addEventListener('teacher-media-audio-status-1014', event => {
    update(event.detail?.status || {});
  });
})();
