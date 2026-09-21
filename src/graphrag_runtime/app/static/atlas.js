(() => {
  'use strict';
  const state = { apiKey: '' };
  const $ = (selector) => document.querySelector(selector);
  const escape = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' })[char]);
  const short = (value, length = 108) => value.length > length ? `${value.slice(0, length - 1)}…` : value;
  const dialog = $('#settings-dialog');
  const query = $('#query');

  function connection(connected) {
    const label = $('#connection-state');
    label.textContent = connected ? 'Connected' : 'Not connected';
    label.classList.toggle('connected', connected);
  }
  function busy(value) {
    const button = $('#search-button');
    button.disabled = value;
    button.querySelector('span').textContent = value ? 'Retrieving evidence…' : 'Search atlas';
  }
  function card(hit) {
    const citations = (hit.citations || []).map((citation) => citation.url
      ? `<a href="${escape(citation.url)}" target="_blank" rel="noopener noreferrer">↗ ${escape(short(citation.title || citation.url))}</a>`
      : `<span>${escape(citation.title || citation.source_id)}</span>`).join('');
    return `<article class="card"><div class="meta"><span class="pill">${escape(hit.collection_label || hit.collection_id)}</span><span>score ${Number(hit.score).toFixed(3)}</span><span class="chunk">${escape(hit.chunk_id)}</span></div><h3>${escape(hit.title)}</h3><p>${escape(hit.text)}</p><div class="citations">${citations || '<span class="muted">No outward citation recorded</span>'}</div></article>`;
  }
  function render(context) {
    $('#empty-state').hidden = true;
    $('#results').hidden = false;
    $('#result-title').textContent = context.query;
    $('#result-count').textContent = `${context.hits.length} evidence ${context.hits.length === 1 ? 'item' : 'items'}`;
    $('#result-list').innerHTML = context.hits.length ? context.hits.map(card).join('') : '<p class="muted">No corpus evidence for this wording. Try a specific instrument, site, parameter, or publication.</p>';
    $('#graph-count').textContent = context.neighbors.length || '—';
    $('#graph-list').innerHTML = context.neighbors.length ? context.neighbors.slice(0, 8).map((item) => `<div class="mini"><span class="edge">${escape(item.predicate)}</span><b>${escape(item.name)}</b><small>${escape(item.collection_id)} · ${escape(item.direction)} · ${item.depth} hop</small></div>`).join('') : '<p class="muted">No graph neighbors returned for these evidence seeds.</p>';
    $('#tool-count').textContent = context.tool_hints.length || '—';
    $('#tool-list').innerHTML = context.tool_hints.length ? context.tool_hints.map((tool) => `<div class="mini"><b>${escape(tool.name)}</b><small>${escape(tool.description)}</small><small>Needs: ${escape((tool.required_arguments || []).join(', ') || 'no arguments')}</small></div>`).join('') : '<p class="muted">No live tool is needed for this corpus-first question.</p>';
  }
  async function search(question) {
    if (!state.apiKey) { dialog.showModal(); $('#api-key').focus(); return; }
    busy(true);
    try {
      const response = await fetch('/v1/context', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-API-Key': state.apiKey }, body: JSON.stringify({ query: question, limit: 8, graph_hops: 1, neighbors_per_seed: 6, tool_limit: 3 }) });
      if (response.status === 401) { state.apiKey = ''; connection(false); dialog.showModal(); $('#settings-error').textContent = 'That key was not accepted. Check your local .env configuration.'; return; }
      if (!response.ok) throw new Error(`The service returned ${response.status}.`);
      render(await response.json());
    } catch (error) {
      $('#empty-state').hidden = false;
      $('#empty-state h2').textContent = 'Could not retrieve evidence.';
      $('#empty-state p').textContent = error.message || 'Check that the local API is running, then try again.';
    } finally { busy(false); }
  }
  $('#settings-button').addEventListener('click', () => { $('#settings-error').textContent = ''; dialog.showModal(); $('#api-key').focus(); });
  $('#settings-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const candidate = $('#api-key').value.trim();
    if (!candidate) { $('#settings-error').textContent = 'Enter the API key from your local .env file.'; return; }
    $('#connect-button').disabled = true;
    try {
      const response = await fetch('/v1/context', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-API-Key': candidate }, body: JSON.stringify({ query: 'RCA Atlas health check', limit: 1, graph_hops: 0, tool_limit: 0 }) });
      if (!response.ok) throw new Error('The API key was not accepted.');
      state.apiKey = candidate; $('#api-key').value = ''; connection(true); dialog.close();
    } catch (error) { $('#settings-error').textContent = error.message; }
    finally { $('#connect-button').disabled = false; }
  });
  $('#query-form').addEventListener('submit', (event) => { event.preventDefault(); const value = query.value.trim(); if (value) search(value); });
  document.addEventListener('keydown', (event) => { if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') { event.preventDefault(); $('#query-form').requestSubmit(); } });
  document.querySelectorAll('[data-question]').forEach((button) => button.addEventListener('click', () => { query.value = button.dataset.question; query.focus(); }));
  document.querySelectorAll('.rail-item').forEach((button) => button.addEventListener('click', () => { document.querySelectorAll('.rail-item').forEach((item) => item.classList.remove('active')); button.classList.add('active'); const target = button.dataset.panel === 'graph' ? $('#graph-panel') : button.dataset.panel === 'tools' ? $('#tool-panel') : $('#results').hidden ? $('#query-form') : $('#results'); target.scrollIntoView({ behavior: 'smooth', block: 'start' }); }));
})();
