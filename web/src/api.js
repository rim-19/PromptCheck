const BASE = "/api";

async function getJSON(path) {
  const r = await fetch(BASE + path);
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

export const api = {
  suites: () => getJSON("/suites"),
  suite: (name) => getJSON(`/suites/${encodeURIComponent(name)}`),
  diff: (baseId, curId) => getJSON(`/runs/${baseId}/diff/${curId}`),
};
