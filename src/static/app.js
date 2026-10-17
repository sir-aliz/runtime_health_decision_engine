'use strict';
const $ = id => document.getElementById(id);
const utc = value => new Date(value).toISOString().replace('T', ' ').replace('.000Z', ' UTC');
const pct = value => value == null ? 'No observations' : `${(value * 100).toFixed(1)}%`;
const ms = value => value == null ? 'No observations' : `${Math.round(value).toLocaleString()} ms`;
let selected = location.pathname.startsWith('/incidents/') ? decodeURIComponent(location.pathname.split('/')[2]) : null;
let requestSequence = 0;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text != null) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function list(id, values) { $(id).replaceChildren(...values.map(value => element('li', value))); }
async function json(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(response.status === 404 ? 'This deployment could not be found. Select another release.' : `Unable to load evidence (${response.status}). Try refreshing.`);
  return response.json();
}
function svgElement(tag, attrs, text) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  if (text != null) node.textContent = text;
  return node;
}
function chart(data, field, label, format, color) {
  const wrapper = element('div');
  wrapper.append(element('p', label, 'chart-label'));
  const svg = svgElement('svg', {viewBox: '0 0 760 155', role: 'img', 'aria-label': `${label} across the deployment`, class: 'chart'});
  const start = Date.parse(data.before.start), end = Date.parse(data.after.end);
  const points = data.timeline.filter(point => point[field] != null && Date.parse(point.timestamp) <= end && Date.parse(point.timestamp) - point.interval_seconds * 1000 >= start);
  const max = Math.max(field === 'error_rate' ? 0.1 : 500, ...points.map(point => point[field])) * 1.15;
  const x = timestamp => 65 + (timestamp - start) / (end - start) * 670;
  const y = value => 115 - value / max * 95;
  for (const value of [0, max / 2, max]) {
    svg.append(svgElement('line', {x1: 65, y1: y(value), x2: 735, y2: y(value), stroke: '#e5ede8'}));
    svg.append(svgElement('text', {x: 55, y: y(value) + 4, 'text-anchor': 'end', fill: '#607478', 'font-size': 10}, format(value)));
  }
  const releaseX = x(Date.parse(data.deployment.timestamp));
  svg.append(svgElement('line', {x1: releaseX, y1: 12, x2: releaseX, y2: 120, stroke: '#71877d', 'stroke-dasharray': '4 4'}));
  for (const point of points) {
    const bucketEnd = Date.parse(point.timestamp), bucketStart = bucketEnd - point.interval_seconds * 1000;
    const bar = svgElement('rect', {x: x(bucketStart) + 1, y: y(point[field]), width: Math.max(1, x(bucketEnd) - x(bucketStart) - 2), height: Math.max(1, 115 - y(point[field])), fill: color, opacity: 0.8, rx: 2});
    bar.append(svgElement('title', {}, `${utc(point.timestamp)} · ${format(point[field])} · ${point.request_count} requests`));
    svg.append(bar);
  }
  for (const [timestamp, text] of [[start, '−10 min'], [Date.parse(data.deployment.timestamp), 'Deployment'], [end, '+10 min']]) {
    svg.append(svgElement('text', {x: x(timestamp), y: 142, 'text-anchor': 'middle', fill: '#607478', 'font-size': 11}, text));
  }
  if (!points.length) svg.append(svgElement('text', {x: 400, y: 65, 'text-anchor': 'middle', fill: '#607478', 'font-size': 13}, 'No observations in this window'));
  wrapper.append(svg);
  return wrapper;
}
function render(data) {
  $('service').textContent = data.deployment.service_id;
  $('release').textContent = `${data.deployment.previous_version} → ${data.deployment.version} · ${utc(data.deployment.timestamp)}`;
  $('decision').textContent = data.decision;
  $('recommendation').className = 'recommendation ' + (data.decision === 'Consider rollback' ? 'critical' : data.decision === 'Insufficient evidence' ? 'neutral' : data.decision.startsWith('Investigate') ? 'warning' : '');
  list('reasons', data.reasons); list('evidence', data.evidence); list('checks', data.checks); list('limitations', data.limitations);
  const rows = [
    ['Error rate', pct(data.before.error_rate), pct(data.after.error_rate)],
    ['Mean latency', ms(data.before.latency_ms), ms(data.after.latency_ms)],
    ['Requests', data.before.request_count.toLocaleString(), data.after.request_count.toLocaleString()],
    ['Window coverage', pct(data.before.coverage), pct(data.after.coverage)],
    ['Health', data.before.health, data.after.health],
  ];
  $('comparison').replaceChildren(...rows.map(values => { const tr = element('tr'); tr.append(...values.map(value => element('td', value))); return tr; }));
  $('charts').replaceChildren(chart(data, 'error_rate', 'Error rate', pct, '#ad6449'), chart(data, 'latency_ms', 'Mean latency', ms, '#2d8475'));
  $('rules').textContent = `Each window needs at least ${data.policy.min_requests} requests and ${data.policy.min_coverage * 100}% coverage. Error regression: ${data.policy.error_regression}. Latency regression: ${data.policy.latency_regression}. Multiple deployments prevent attribution. A degraded baseline or either of its final two nonempty buckets prompts investigation of an existing incident.`;
  $('incident').hidden = false;
}
async function load() {
  const sequence = ++requestSequence;
  $('status').textContent = 'Loading evidence…'; $('status').className = '';
  $('incident').hidden = true; $('empty').hidden = true;
  try {
    const deployments = await json('/deployments');
    if (sequence !== requestSequence) return;
    if (!selected && deployments.length) selected = deployments[0].id;
    $('deployments').replaceChildren(...deployments.map(deployment => {
      const link = element('a'); link.href = `/incidents/${encodeURIComponent(deployment.id)}`;
      if (deployment.id === selected) link.setAttribute('aria-current', 'page');
      link.append(element('strong', deployment.service_id), element('span', `${deployment.previous_version} → ${deployment.version}`));
      link.addEventListener('click', event => {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault(); selected = deployment.id; history.pushState({}, '', link.href); load();
      });
      return link;
    }));
    if (!selected) { $('empty').hidden = false; $('status').textContent = ''; return; }
    const data = await json(`/deployments/${encodeURIComponent(selected)}/analysis`);
    if (sequence !== requestSequence) return;
    render(data); $('status').textContent = '';
  } catch (error) {
    if (sequence !== requestSequence) return;
    $('status').textContent = error.message; $('status').className = 'error';
  }
}
$('refresh').addEventListener('click', load);
window.addEventListener('popstate', () => { selected = location.pathname.startsWith('/incidents/') ? decodeURIComponent(location.pathname.split('/')[2]) : null; load(); });
load();
