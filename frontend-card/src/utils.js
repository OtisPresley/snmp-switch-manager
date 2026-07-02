// Internal: normalize config without changing behavior.
// This provides a single canonical place to evolve config handling over time.

// Internal: natural-ish compare for interface names like Gi1/0/2 vs Gi1/0/10.
// Splits into alpha and numeric tokens and compares token-by-token.
function _ssmNaturalPortCompare(a, b) {
  const sa = String(a ?? "");
  const sb = String(b ?? "");
  if (sa === sb) return 0;

  const ta = sa.match(/(\d+|[^\d]+)/g) || [sa];
  const tb = sb.match(/(\d+|[^\d]+)/g) || [sb];
  const n = Math.max(ta.length, tb.length);

  for (let i = 0; i < n; i++) {
    const xa = ta[i];
    const xb = tb[i];
    if (xa == null) return -1;
    if (xb == null) return 1;

    const na = /^\d+$/.test(xa);
    const nb = /^\d+$/.test(xb);

    if (na && nb) {
      const ia = parseInt(xa, 10);
      const ib = parseInt(xb, 10);
      if (ia !== ib) return ia - ib;
      // same numeric value but different width (e.g., 01 vs 1)
      if (xa.length !== xb.length) return xa.length - xb.length;
    } else if (!na && !nb) {
      const ca = xa.localeCompare(xb, undefined, { sensitivity: "base" });
      if (ca !== 0) return ca;
    } else {
      // put alpha tokens before numeric tokens for stability
      return na ? 1 : -1;
    }
  }

  return sa.localeCompare(sb, undefined, { sensitivity: "base" });
}

function _ssmNormalizeConfig(config) {
  // IMPORTANT: do not introduce new defaults here unless they already exist implicitly
  // in the card/editor behavior. Keep this behavior-preserving.
  if (!config || typeof config !== "object") return {};
  // Shallow clone to avoid accidental external mutation.
  const out = { ...config };

// Port gap: canonical keys (preferred). Older keys are mapped once for backward compatibility.
// Official keys: horizontal_port_gap, vertical_port_gap
const hasH = out.horizontal_port_gap != null && out.horizontal_port_gap !== "";
const hasV = out.vertical_port_gap != null && out.vertical_port_gap !== "";
if (!hasH || !hasV) {
  // Backward compat sources (deprecated): port_gap_x/y, gap_x/y, gap
  const legacyH = (out.port_gap_x ?? out.gap_x ?? out.gap);
  const legacyV = (out.port_gap_y ?? out.gap_y ?? out.gap);
  if (!hasH && legacyH != null && legacyH !== "") out.horizontal_port_gap = legacyH;
  if (!hasV && legacyV != null && legacyV !== "") out.vertical_port_gap = legacyV;
}

  // Drop deprecated / renamed keys to keep saved YAML clean.
  // Keep this list explicit (do not strip unknown future keys).
  const deprecatedKeys = [
    "port_gap_y",
    "port_gap_x",
    "gap_y",
    "gap_x",
    "gap",
    "show_uplinks_separately_in_layout", // old/typo key
  ];
  for (const k of deprecatedKeys) {
    if (k in out) delete out[k];
  }

  return out;
}



function _ssmNormListToSet(v) {
  // Accept array of strings, comma-separated string, or null/undefined.
  const out = new Set();
  if (Array.isArray(v)) {
    for (const it of v) {
      const k = String(it ?? "").trim().toLowerCase();
      if (k) out.add(k);
    }
    return out;
  }
  if (typeof v === "string") {
    for (const part of v.split(",")) {
      const k = String(part ?? "").trim().toLowerCase();
      if (k) out.add(k);
    }
  }
  return out;
}


function _ssmIsHiddenPort(config, portName, entityId) {
  try {
    const set = _ssmNormListToSet(config?.hide_ports);
    if (!set || set.size === 0) return false;
    const n = String(portName ?? "").trim().toLowerCase();
    const e = String(entityId ?? "").trim().toLowerCase();
    return (n && set.has(n)) || (e && set.has(e));
  } catch (e) {
    return false;
  }
}



// Robust, prefix-and-casing-insensitive uplink port checker
function _ssmIsUplinkPort(uplinkSet, portName, entityId, card) {
  if (!uplinkSet || !uplinkSet.size) return false;

  const clean = (s) => {
    let v = String(s ?? "").trim().toLowerCase();
    v = v.replace(/gigabitethernet/g, "gi");
    v = v.replace(/fastethernet/g, "fa");
    v = v.replace(/tengigabitethernet/g, "te");
    v = v.replace(/fortygigabitethernet/g, "fo");
    v = v.replace(/hundredgigabitethernet/g, "hu");
    v = v.replace(/ethernet/g, "eth");
    if (card && typeof card._stripDiagPrefix === "function") {
      v = card._stripDiagPrefix(v);
    }
    return v.replace(/[^a-z0-9]/g, "");
  };

  const getPortNum = (s) => {
    const m = String(s || "").match(/(\d+)(?!.*\d)/);
    return m ? m[1] : null;
  };

  const normalizePrefix = (p) => {
    if (!p) return "";
    let v = p.toLowerCase();
    if (v === "gigabitethernet" || v === "gi") return "gi";
    if (v === "fastethernet" || v === "fa") return "fa";
    if (v === "tengigabitethernet" || v === "te") return "te";
    if (v === "twentygigabitethernet" || v === "tw") return "tw";
    if (v === "fortygigabitethernet" || v === "fo") return "fo";
    if (v === "hundredgigabitethernet" || v === "hu") return "hu";
    if (v === "ethernet" || v === "eth") return "eth";
    return v;
  };

  const cleanAndParse = (s) => {
    if (!s) return null;
    let v = String(s).trim().toLowerCase();
    if (card && typeof card._stripDiagPrefix === "function") {
      v = card._stripDiagPrefix(v);
    }
    const match = v.match(/^([a-z]+)?\s*(.*?)$/);
    if (!match) return null;
    const prefix = normalizePrefix(match[1] || "");
    const rest = match[2] || "";
    const parts = rest.split(/[^0-9]+/).filter(x => x !== "");
    return { prefix, parts };
  };

  const entityTail = String(entityId ?? "").split(".")[1] || "";
  const cName = clean(portName);
  const cTail = clean(entityTail);
  const cEntity = clean(entityId);
  const parsedName = cleanAndParse(portName);
  const parsedTail = cleanAndParse(entityTail);
  const parsedEntity = cleanAndParse(entityId);
  const numName = getPortNum(portName);
  const numTail = getPortNum(entityTail);

  const UPLINK_PREFIXES = new Set(["te", "tw", "fo", "hu", "sfp", "xg", "eth"]);
  const EXCLUDED_PREFIXES = new Set(["gi", "fa"]);

  for (const item of uplinkSet) {
    const cItem = clean(item);
    if (!cItem) continue;
    if (cItem === cName || cItem === cTail || cItem === cEntity) return true;
    const parsedItem = cleanAndParse(item);
    if (parsedItem) {
      const tryMatchParsed = (parsedPort) => {
        if (!parsedPort) return false;
        if (parsedPort.parts.length === parsedItem.parts.length &&
            parsedPort.parts.every((p, idx) => p === parsedItem.parts[idx])) {
          if (UPLINK_PREFIXES.has(parsedPort.prefix) && UPLINK_PREFIXES.has(parsedItem.prefix)) return true;
        }
        return false;
      };
      const isExcluded = (parsedPort) => {
        if (!parsedPort) return false;
        return EXCLUDED_PREFIXES.has(parsedPort.prefix) || EXCLUDED_PREFIXES.has(parsedItem.prefix);
      };
      if (!isExcluded(parsedName) && tryMatchParsed(parsedName)) return true;
      if (!isExcluded(parsedTail) && tryMatchParsed(parsedTail)) return true;
      if (!isExcluded(parsedEntity) && tryMatchParsed(parsedEntity)) return true;
    }
    if (/^\d+$/.test(String(item).trim())) {
      const numItem = getPortNum(item);
      if (numItem && (numItem === numName || numItem === numTail)) return true;
    }
  }
  return false;
}
