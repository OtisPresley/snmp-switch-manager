// Only register the editor if it isn't already registered.
if (!customElements.get("snmp-switch-manager-card-editor")) {
  customElements.whenDefined("snmp-switch-manager-card").then(() => {
    const CardClass = customElements.get("snmp-switch-manager-card");

    // Tell Home Assistant how to get the editor + a stub config (guarded).
    if (!CardClass.getConfigElement) {
      CardClass.getConfigElement = () => {
        return document.createElement("snmp-switch-manager-card-editor");
      };
    }
    if (!CardClass.getStubConfig) {
      CardClass.getStubConfig = () => ({
        type: "custom:snmp-switch-manager-card",
        title: "SNMP Switch",
        view: "panel",
        color_mode: "state",
        ports_per_row: 24,
        panel_width: 740,
        port_size: 18,
        gap: 10,
        show_labels: true,
        label_numbers_only: false,
        label_size: 8,
        info_position: "above",
        hide_diagnostics: false,
        hide_virtual_interfaces: false,
        calibration_mode: false,
        device: null,
      });
    }

    class SnmpSwitchManagerCardEditor extends HTMLElement {
      constructor() {
        super();
        this.attachShadow({ mode: "open" });
        this._config = {};
        this._hass = null;

        // Flags so we only render ONCE per editor instance
        this._hasConfig = false;
        this._hasHass = false;
        this._rendered = false;

        // Draft state to prevent config churn while typing (prevents focus loss)
        this._editingTitle = false;
        this._draftTitle = null;
        // Cache port entity ids per switch prefix (device) to avoid scanning all hass.states
        this._portEidsByPrefix = null;
        this._didVirtualMigrate = false;
      
        // Listen for saved calibration positions from the live card preview
        this._onSsmPositionsSaved = (ev) => {
          const d = ev && ev.detail ? ev.detail : null;
          if (!d || !d.port_positions || typeof d.port_positions !== "object") return;
          // Match by selected device prefix to avoid cross-talk
          if ((d.device || "") !== (this._config?.device || "")) return;
          
          if (!this._config) this._config = {};
          const newConfig = {
            ...this._config,
            port_positions: d.port_positions,
            viewbox: d.viewbox || null
          };
          this._config = newConfig;
          this.dispatchEvent(
            new CustomEvent("config-changed", {
              detail: { config: newConfig },
              bubbles: true,
              composed: true,
            }),
          );
        };

        // Listen for "exit layout editor" from the live card preview so the toggle resets in the UI
        this._onSsmCalibrationClosed = (ev) => {
          const d = ev && ev.detail ? ev.detail : {};
          if (d.device && this._config?.device && (d.device || "") !== (this._config?.device || "")) return;
          if (!this._isCalibrationEnabled()) return;
          this._updateConfig("calibration_mode", false);
        };

      }

      // ---- Diagnostics auto-default helpers (Editor) ----
      // The live card injects conservative Environment/PoE defaults into the Diagnostics list
      // when the underlying sensors/attributes exist. The editor must mirror that logic so the
      // visual editor doesn't crash and the displayed Diagnostics order matches the live card.

      _inferDevicePrefix() {
        const cfg = this._config || {};
        if (cfg.device) return String(cfg.device);
        const ae = cfg.anchor_entity ? String(cfg.anchor_entity) : "";
        const ent = ae.includes(".") ? ae.split(".")[1] : "";
        const m = ent.match(/^(.+?)_[a-z0-9]+\d/i);
        if (m) return m[1];
        return ent ? ent.split("_")[0] : "";
      }

      _autoDefaultDiagKeys(prefix, H) {
        // Prefer Sensors-mode entities when present; otherwise fall back to Attributes-mode
        // aggregate sensors (Environment + Power over Ethernet) and read specific attributes.
        const out = [];

        // Environment
        const envTemp = `sensor.${prefix}_system_temperature`;
        const envTempStatus = `sensor.${prefix}_system_temperature_status`;
        const envAgg = `sensor.${prefix}_environment`;
        if (H[envTemp]) out.push(envTemp);
        else {
          const st = H[envAgg];
          const v = st?.attributes?.["System Temperature (°C)"];
          if (v != null) out.push(`${envAgg}#System Temperature (°C)`);
        }
        if (H[envTempStatus]) out.push(envTempStatus);
        else {
          const st = H[envAgg];
          const v = st?.attributes?.["System Temperature Status"];
          if (v != null) out.push(`${envAgg}#System Temperature Status`);
        }

        // PoE
        const poeUsed = `sensor.${prefix}_poe_power_used`;
        const poeAvail = `sensor.${prefix}_poe_power_available`;
        const poeAgg = `sensor.${prefix}_power_over_ethernet`;
        if (H[poeUsed]) out.push(poeUsed);
        else {
          const st = H[poeAgg];
          const v = st?.attributes?.["PoE Power Used (W)"];
          if (v != null) out.push(`${poeAgg}#PoE Power Used (W)`);
          else if (st) out.push(poeAgg); // last resort: show aggregate sensor state
        }
        if (H[poeAvail]) out.push(poeAvail);
        else {
          const st = H[poeAgg];
          const v = st?.attributes?.["PoE Power Available (W)"];
          if (v != null) out.push(`${poeAgg}#PoE Power Available (W)`);
        }

        return out;
      }

      _isAutoDefaultDiagKey(key) {
        const k = String(key || "");
        return (
          /_system_temperature(_status)?$/.test(k) ||
          /_poe_power_(used|available)$/.test(k) ||
          /_environment#System Temperature/.test(k) ||
          /_power_over_ethernet#PoE Power (Used|Available)/.test(k) ||
          /_power_over_ethernet$/.test(k)
        );
      }

      _injectAutoDiagDefaults(order, enabledMap) {
        const H = this._hass?.states || {};
        const prefix = this._inferDevicePrefix();
        if (!prefix) return order;

        const defaults = this._autoDefaultDiagKeys(prefix, H);
        if (!defaults.length) return order;

        const out = Array.isArray(order) ? [...order] : [];
        for (const k of defaults) {
          if (enabledMap && enabledMap[k] === false) continue; // respect user removal/disable
          if (!out.includes(k)) out.push(k);
        }
        return out;
      }


      
      _setupAutoScale() {
        // Responsive scale for large displays (e.g., 4K). Defaults ON unless explicitly disabled.
        if (this._ssmResizeObs) return;
        const run = () => this._applyAutoScale();
        // Use ResizeObserver to react to layout changes without polling
        try {
          this._ssmResizeObs = new ResizeObserver(() => {
            if (this._ssmScaleRaf) cancelAnimationFrame(this._ssmScaleRaf);
            this._ssmScaleRaf = requestAnimationFrame(run);
          });
          this._ssmResizeObs.observe(this);
        } catch (e) {
          // Fallback: window resize
          window.addEventListener("resize", run);
          this._ssmResizeFallback = run;
        }
      }

      _applyAutoScale() {
        if (!this.shadowRoot) return;
        if (this._config && this._config.auto_scale === false) return;

        const outer = this.shadowRoot.querySelector(".autoscale-outer");
        const inner = this.shadowRoot.querySelector(".autoscale-inner");
        if (!outer || !inner) return;

        // Ensure we measure unscaled content
        inner.style.transform = "scale(1)";
        outer.style.height = "auto";

        const availW = outer.getBoundingClientRect().width;
        const contentW = inner.scrollWidth;
        const contentH = inner.scrollHeight;

        if (!availW || !contentW) return;

        // Allow upscaling on large displays; cap to avoid absurd zoom.
        const maxScale = 2.5;
        let s = availW / contentW;
        if (!Number.isFinite(s) || s <= 0) s = 1;
        if (s > maxScale) s = maxScale;

        inner.style.transform = `scale(${s})`;
        outer.style.height = `${Math.ceil(contentH * s)}px`;
      }
connectedCallback() {
        if (this._ssmPosListenerAdded) return;
        this._ssmPosListenerAdded = true;
        window.addEventListener("ssm-port-positions-saved", this._onSsmPositionsSaved);
        window.addEventListener("ssm-calibration-closed", this._onSsmCalibrationClosed);
        this._setupAutoScale();
      }

      disconnectedCallback() {
        if (!this._ssmPosListenerAdded) return;
        this._ssmPosListenerAdded = false;
        window.removeEventListener("ssm-port-positions-saved", this._onSsmPositionsSaved);
        window.removeEventListener("ssm-calibration-closed", this._onSsmCalibrationClosed);
        if (this._ssmResizeObs) {
          try { this._ssmResizeObs.disconnect(); } catch (e) {}
          this._ssmResizeObs = null;
        }
      }

      _defaultSpeedPalette() {
        return {
          "10 Mbps": "#9ca3af",
          "100 Mbps": "#f59e0b",
          "1 Gbps": "#22c55e",
          "2.5 Gbps": "#14b8a6",
          "5 Gbps": "#0ea5e9",
          "10 Gbps": "#3b82f6",
          "20 Gbps": "#6366f1",
          "25 Gbps": "#8b5cf6",
          "40 Gbps": "#a855f7",
          "50 Gbps": "#d946ef",
          "100 Gbps": "#ec4899",
          "Unknown": "#ef4444",
        };
      }



      _stateLabel(key) {
        switch (key) {
          case "up_up": return "Up/Up";
          case "up_down": return "Up/Down";
          case "down_down": return "Admin Down";
          case "up_not_present": return "Not Present";
          default: return key;
        }
      }

      _diagnosticLabel(key) {
      const k = String(key || "");
      const map = {
        hostname: "Hostname",
        manufacturer: "Manufacturer",
        model: "Model",
        firmware: "Firmware Revision",
        firmware_revision: "Firmware Revision",
        uptime: "Uptime",
      };
      if (map[k]) return map[k];
      if (this._hass && this._hass.states && this._hass.states[k]) {
        return this._hass.states[k].attributes.friendly_name || k;
      }
      return k;
    }


      _defaultStatePalette() {
        // Defaults match the card's current state mode legend.
        // Keys are internal and stable; UI can present friendly labels.
        return {
          "up_up": "#22c55e",           // Green — Admin: Up • Oper: Up
          "up_down": "#ef4444",         // Red — Admin: Up • Oper: Down
          "down_down": "#f59e0b",       // Orange — Admin: Down • Oper: Down
          "up_not_present": "#9ca3af",  // Gray — Admin: Up • Oper: Not Present
        };
      }


      _speedLabelFromAttrs(attrs) {
        if (!attrs) return null;
        const candidates = [
          attrs.SpeedLabel, attrs.speed_label, attrs.speedLabel, attrs.speedText, attrs.speed_text, attrs.SpeedDisplay, attrs.speed_display, attrs.speedDisplay,
          attrs.LinkSpeedLabel, attrs.link_speed_label, attrs.LinkSpeedText, attrs.link_speed_text,
          attrs.PortSpeedLabel, attrs.port_speed_label,
          attrs.Speed, attrs.speed, attrs.PortSpeed, attrs.port_speed, attrs.link_speed, attrs.LinkSpeed,
          attrs.ifSpeed, attrs.if_speed
        ].filter(v => v != null);

        for (const raw of candidates) {
          if (typeof raw !== "string") continue;
          const s0 = raw.trim();
          if (!s0) continue;
          const s = s0.replace(/\s+/g, " ").trim();
          const compact = s.toLowerCase().replace(/\s+/g, "");
          const m = compact.match(/^([0-9]+(?:\.[0-9]+)?)(m|g)bps$/);
          if (m) return `${m[1]} ${(m[2] === "g") ? "Gbps" : "Mbps"}`;
          if (/^[0-9]+(?:\.[0-9]+)?\s*(m|g)bps$/i.test(s)) {
            const mm = s.match(/^([0-9]+(?:\.[0-9]+)?)\s*(m|g)bps$/i);
            return `${mm[1]} ${(mm[2].toLowerCase() === "g") ? "Gbps" : "Mbps"}`;
          }
        }
        return null;
      }


_allSupportedSpeedLabels() {
  const palette = this._defaultSpeedPalette();
  const labels = new Set(Object.keys(palette || {}));
  labels.add("Disconnected");
  labels.add("Admin Down");

  // Sort ascending by Mbps
  const toMbps = (lab) => {
    if (typeof lab === "number") return lab;
    if (lab === "Admin Down") return -2;
    if (lab === "Admin Down") return -2;
    if (lab === "Disconnected") return -1;
    const s = String(lab);
    const m = s.match(/^([0-9]+(?:\.[0-9]+)?)\s*(M|G)bps$/i);
    if (!m) return Number.POSITIVE_INFINITY;
    const v = parseFloat(m[1]);
    const unit = m[2].toLowerCase();
    return unit === "g" ? v * 1000 : v;
  };

  return Array.from(labels).sort((a, b) => toMbps(a) - toMbps(b));
}

_detectedSpeedLabels(devicePrefix) {
  const hass = this._hass;
  const labels = new Set();

  const map = (this._portEidsByPrefix instanceof Map) ? this._portEidsByPrefix : null;
  if (!map || !hass?.states) return [];

  const prefix = String(devicePrefix || "");
  const wantAll = !prefix || prefix === "all";

  const addFromList = (list) => {
    if (!Array.isArray(list) || !list.length) return;
    for (const eid of list) {
      const st = hass.states[eid];
      if (!st) continue;
      const label = this._speedLabelFromAttrs(st?.attributes) || null;
      if (label) labels.add(label);
    }
  };

  if (wantAll) {
    for (const list of map.values()) addFromList(list);
  } else {
    addFromList(map.get(prefix) || null);
  }

  // Sort ascending by Mbps
  const toMbps = (lab) => {
    if (typeof lab === "number") return lab;
    if (lab === "Disconnected") return -1;
    const s = String(lab);
    const m = s.match(/^([0-9]+(?:\.[0-9]+)?)\s*(M|G)bps$/i);
    if (!m) return Number.POSITIVE_INFINITY;
    const v = parseFloat(m[1]);
    const unit = m[2].toLowerCase();
    return unit === "g" ? v * 1000 : v;
  };
    labels.add("Disconnected");
  labels.add("Admin Down");
  return Array.from(labels).sort((a, b) => toMbps(a) - toMbps(b));
}

  _renderStateColorsSection(c) {
        const palette = this._defaultStatePalette();
        const overrides = (c.state_colors && typeof c.state_colors === "object") ? c.state_colors : {};
        const keys = ["up_up", "up_down", "down_down", "up_not_present"];

        const items = keys.map((k) => {
          const val = (typeof overrides[k] === "string" && overrides[k].trim())
            ? overrides[k].trim()
            : (palette[k] || "#9ca3af");
          return `
            <div class="colorItem">
              <div class="colorTitle">${this._escape(this._stateLabel(k))}</div>
              <div class="colorControls">
                <input class="statecolor" type="color" data-state="${this._escape(k)}" value="${this._escape(val)}" />
                <input class="statehex" type="text" maxlength="7" data-state="${this._escape(k)}" value="${this._escape(val)}" />
              </div>
            </div>
          `;
        }).join("");

        const hasOverrides = c.state_colors && typeof c.state_colors === "object" && Object.keys(c.state_colors).length > 0;

        return `
          <div class="row">
            <div class="rowhead">
              <label>State colors</label>
              <button id="state_reset" class="iconbtn sm" type="button" title="Reset to defaults"${hasOverrides ? "" : " disabled"}>
                <ha-icon icon="mdi:restore"></ha-icon>
              </button>
            </div>
            <div class="hint">Customize the colors used when Color mode is set to State.</div>
            <div class="colorGrid">${items}</div>
          </div>
        `;
      }




      _renderSpeedColorsSection(c) {
        const palette = this._defaultSpeedPalette();
        const overrides = (c.speed_colors && typeof c.speed_colors === "object") ? c.speed_colors : {};
        const labels = (c.show_all_speeds === true) ? this._allSupportedSpeedLabels() : this._detectedSpeedLabels(c.device);

        const items = labels.map((lab) => {
          const o = (typeof overrides[lab] === "string" && overrides[lab].trim())
            ? overrides[lab].trim()
            : null;
          const o2 = (lab === "Disconnected" && typeof overrides["Unknown"] === "string" && overrides["Unknown"].trim())
            ? overrides["Unknown"].trim()
            : null;
          const val = o || o2 || (palette[lab] || palette["Disconnected"] || palette["Unknown"] || "#ef4444");
          return `
            <div class="colorItem">
              <div class="colorTitle">${this._escape(lab)}</div>
              <div class="colorControls">
                <input class="speedcolor" type="color" data-speed="${this._escape(lab)}" value="${this._escape(val)}" />
                <input class="speedhex" type="text" maxlength="7" data-speed="${this._escape(lab)}" value="${this._escape(val)}" />
              </div>
            </div>
          `;
        }).join("");

        const hasOverrides = c.speed_colors && typeof c.speed_colors === "object" && Object.keys(c.speed_colors).length > 0;

        return `
          <div class="row">
            <div class="rowhead">
              <label>Speed colors</label>
              <button id="speed_reset" class="iconbtn sm" type="button" title="Reset to defaults"${hasOverrides ? "" : " disabled"}>
                <ha-icon icon="mdi:restore"></ha-icon>
              </button>
            </div>
            
            <div class="row inline" style="align-items:center;gap:10px;margin-top:8px;">
              <label for="show_all_speeds" style="margin:0;">Show all speeds</label>
              <ha-switch id="show_all_speeds"${c.show_all_speeds ? " checked" : ""}></ha-switch>
            </div>
            <div class="hint">Colors are based on the switch's normalized speed labels. When "Show all speeds" is on, the full supported set is shown even if the device hasn’t reported that speed yet.</div>
            <div class="colorGrid">${items}</div>
          </div>
        `;
      }



      set hass(c) {
        const palette = this._defaultSpeedPalette();
        const overrides = (c.speed_colors && typeof c.speed_colors === "object") ? c.speed_colors : {};
        const labels = this._detectedSpeedLabels(c.device);
        const rows = labels.map((lab) => {
          const val = (typeof overrides[lab] === "string" && overrides[lab].trim())
            ? overrides[lab].trim()
            : (palette[lab] || palette["Disconnected"]);
          return `
            <div class="speedrow">
              <div class="speedlabel">${this._escape(lab)}</div>
              <input class="speedcolor" type="color" data-speed="${this._escape(lab)}" value="${this._escape(val)}" />
              <input class="speedhex" type="text" data-speed="${this._escape(lab)}" value="${this._escape(val)}" />
            </div>
          `;
        }).join("");

        const hasOverrides = c.speed_colors && typeof c.speed_colors === "object" && Object.keys(c.speed_colors).length > 0;

        return `
          <div class="row">
            <label>Speed colors</label>
            <div class="hint">Colors are based on the switch's normalized speed labels. Only speeds detected on the selected device are shown (or across all devices when none is selected).</div>
            <div class="speedgrid">${rows}</div>
            <div class="row inline">
              <button id="speed_reset" class="btn" type="button"${hasOverrides ? "" : " disabled"}>Reset to defaults</button>
            </div>
          </div>
        `;
      }

      set hass(hass) {
        // Keep hass (editor API) but **do not** re-render on every state change.
        // HA updates hass very frequently; rebuilding the editor DOM causes inputs / datalist
        // selections to disappear mid-typing (the "refresh" issue).
        const first = !this._hasHass;
        this._hass = hass;
        this._hasHass = true;

        if (first) {
          this._loadSnmpDevices();
        }

        if (!this._hasConfig) return;

        // Only re-render when the *available ports list* changes for the selected device.
        // This keeps the datalist current without nuking the UI on unrelated state updates.
        const dev = (this._config?.device || "").toString();
        const ports = dev ? (this._getPortsForDevice(dev) || []) : [];
        const sig = dev + "::" + ports.join("|");
        if (sig !== this._lastPortsSig) {
          this._lastPortsSig = sig;
          this._render();
        }
      }

      setConfig(config) {
        config = _ssmNormalizeConfig(config);

        this._config = { ...config };

        // Hydrate Layout positions from localStorage so they persist when the user clicks Save in the HA editor.
// This is critical because Layout Editor changes can happen outside the HA config dialog.
// NOTE: Use the same storage key logic as the runtime layout loader (v3 + draft, with legacy v2 fallback),
// otherwise editor re-renders can overwrite the preview with stale saved positions.
try {
  const stored = this._loadCalibMapFromStorage();
  const map = (stored && stored.map && typeof stored.map === "object") ? stored.map : null;
  if (map) {
    this._config.port_positions = map;
  }
} catch (e) {}
// If the user closed the Layout Editor from the live card, reset the toggle here so it persists.
// IMPORTANT: do NOT clear the flag until the config actually has calibration_mode=false saved,
// otherwise "Cancel" in the HA editor would resurrect the old YAML value.
try {
  const prefix = (this._config?.device || "") ? String(this._config.device) : "all";
  const k = `ssm_calib_force_off:${prefix}`;
  const ts = localStorage.getItem(k);

  // If we already see calibration_mode=false coming from YAML, clear the one-shot flag.
  if (ts && !this._config?.calibration_mode) {
    localStorage.removeItem(k);
  }

  // If YAML still says true, force it off in the editor view (and keep the flag)
  // so it stays off across cancel/re-open until the user saves.
  if (ts && this._config?.calibration_mode) {
    setTimeout(() => {
      try { this._updateConfig("calibration_mode", false); } catch (e) {}
    }, 0);
  }
} catch (e) {}

        if (!this._editingTitle) {
          this._draftTitle = null;
        }

        this._hasConfig = true;
        // Re-render when config changes so lists + preview stay in sync.
        if (this._hasHass) {
          this._render();
        }
      }

      // ---- helpers ----

async _loadSnmpDevices() {
  if (this._loadingDevices) return;
  if (!this._hass) return;

  // Cache once per editor instance; keep it simple & robust.
  if (Array.isArray(this._snmpDevices)) return;

  this._loadingDevices = true;
  try {
    // 1) Find SNMP Switch Manager config entry ids
    const entries = await this._hass.callWS({ type: "config_entries/get" });
    const entryIds = (entries || [])
      .filter(e => e && e.domain === "snmp_switch_manager")
      .map(e => e.entry_id);

    // 2) List devices and filter to those attached to the SNMP Switch Manager entries
    const devices = await this._hass.callWS({ type: "config/device_registry/list" });
    const snmpDevices = (devices || []).filter(d =>
      Array.isArray(d?.config_entries) && d.config_entries.some(id => entryIds.includes(id))
    );

    // 3) Map device -> hostname prefix by looking at entity registry entries attached to that device
    //    (We only need a stable prefix so the card can scope ports/sensors by entity_id.)
    const entityReg = await this._hass.callWS({ type: "config/entity_registry/list" });
    const byDevice = new Map();
    for (const ent of (entityReg || [])) {
      const did = ent?.device_id;
      const eid = ent?.entity_id;
      if (!did || !eid) continue;
      if (!byDevice.has(did)) byDevice.set(did, []);
      byDevice.get(did).push(eid);
    }

    const result = [];
    const portEidsByPrefix = new Map();
    for (const d of snmpDevices) {
      const id = d.id;
      const name = d.name_by_user || d.name || id;

      // Prefer a hostname sensor if present; else fall back to a switch entity.
      const eids = byDevice.get(id) || [];
      let prefix = "";
      for (const eid of eids) {
        const m = String(eid).match(/^sensor\.([a-z0-9_]+)_(hostname|device_info|device_information)$/i);
        if (m) { prefix = m[1]; break; }
      }
      if (!prefix) {
        for (const eid of eids) {
          const m = String(eid).match(/^switch\.([a-z0-9_]+)_/i);
          if (m) { prefix = m[1]; break; }
        }
      }

      // If we can't derive a prefix, skip it (prevents "empty selection" that breaks scoping).
      if (!prefix) continue;

      const portEids = eids.filter(eid => String(eid).startsWith(`switch.${prefix}_`));
      portEidsByPrefix.set(prefix, portEids);
      result.push({ id, name, prefix, portEids });
    }

    result.sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" }));
    this._snmpDevices = result;
    this._portEidsByPrefix = portEidsByPrefix;
  } catch (err) {
    // If anything fails, keep an empty list (but do not break the card/editor).
    // eslint-disable-next-line no-console
    console.warn("SNMP Switch Manager Card: failed to load devices", err);
    this._snmpDevices = [];
    this._portEidsByPrefix = new Map();
  } finally {
    this._loadingDevices = false;
    // Re-render once after devices load; do not flip _rendered back to false.
    this._render();
  }
}

_listDevicesFromHass() {
  // Back-compat fallback: return any cached SNMP devices prefixes.
  const list = Array.isArray(this._snmpDevices) ? this._snmpDevices : [];
  return list.map(d => d.prefix);
}

      _escape(str) {
        if (str == null) return "";
        return String(str)
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/\"/g, "&quot;");
      }        // Restore focus after re-render (best-effort).
        if (_activeId) {
          const el = this.shadowRoot.getElementById(_activeId);
          if (el && typeof el.focus === "function") {
            el.focus();
            if (_activeSel && typeof el.setSelectionRange === "function") {
              try { el.setSelectionRange(_activeSel.start, _activeSel.end); } catch(e) {}
            }
          }
        }


      _updateConfig(key, value) {
        if (!this._config) this._config = {};
        const newConfig = { ...this._config, [key]: value };
        this._config = newConfig;
        this.dispatchEvent(
          new CustomEvent("config-changed", {
            detail: { config: newConfig },
            bubbles: true,
            composed: true,
          }),
        );
        // IMPORTANT: no re-render here – we keep the DOM as-is
      }

      _portsForPrefix(prefix) {
        const hass = this._hass;
        const pfx = String(prefix || "").trim();
        if (!hass || !pfx) return [];
        const pre = `switch.${pfx.toLowerCase()}_`;
        const out = [];
        // Scan only entities matching the selected device prefix (bounded, low risk)
        for (const [eid, st] of Object.entries(hass.states || {})) {
          if (!eid || typeof eid !== "string") continue;
          if (!eid.toLowerCase().startsWith(pre)) continue;
          const a = st && st.attributes ? st.attributes : {};
          const name = String(a.Name || "").trim();
          if (!name) continue;
          out.push({ name, entity_id: eid });
        }
        // Sort naturally by last number when possible
        out.sort((aa, bb) => {
          const a = aa.name, b = bb.name;
          const ma = a.match(/(\d+)(?!.*\d)/), mb = b.match(/(\d+)(?!.*\d)/);
          const na = ma ? parseInt(ma[1], 10) : NaN;
          const nb = mb ? parseInt(mb[1], 10) : NaN;
          if (Number.isFinite(na) && Number.isFinite(nb) && na !== nb) return na - nb;
          return a.localeCompare(b);
        });
        return out;
      }

      _deviceHasBandwidthSensors(prefix) {
        const hass = this._hass;
        const pfx = String(prefix || "").trim().toLowerCase();
        if (!hass || !pfx) return false;

        // Bandwidth sensor entity_ids are derived from the device prefix, but may not
        // share the same base as the per-port switch entity_id on all vendors.
        // We consider bandwidth "available" if we can find any RX/TX throughput pair
        // for this device prefix.
        const rxSuffix = "_rx_throughput";
        const states = hass.states || {};
        for (const eid of Object.keys(states)) {
          if (!eid || typeof eid !== "string") continue;
          const e = eid.toLowerCase();
          if (!e.startsWith(`sensor.${pfx}_`)) continue;
          if (!e.endsWith(rxSuffix)) continue;

          const tx = eid.slice(0, -rxSuffix.length) + "_tx_throughput";
          if (states[tx]) return true;
        }
        return false;
      }




      _render() {
        if (!this.shadowRoot) return;
        // Preserve focused field across re-renders (prevents losing focus while editing)
        const _active = this.shadowRoot.activeElement;
        const _activeId = _active && _active.id ? _active.id : null;
        const _activeSel = (_active && typeof _active.selectionStart === 'number') ? { start: _active.selectionStart, end: _active.selectionEnd } : null;
        let c = this._config || {};
        const devices = Array.isArray(this._snmpDevices) ? this._snmpDevices : [];
        const deviceOptions = devices.map(d => {
          const sel = String(c.device || "") === String(d.prefix) ? " selected" : "";
          return `<option value="${this._escape(d.prefix)}"${sel}>${this._escape(d.name)}</option>`;
        }).join("");

        const portChoices = this._portsForPrefix(String(c.device || ""));
        const _hasBandwidth = (c.color_mode === "speed") && this._deviceHasBandwidthSensors(String(c.device || ""));

        const portNameChoices = portChoices.map(p => String(p.name || "").trim()).filter(Boolean);
        portNameChoices.sort(_ssmNaturalPortCompare);
        // One-time migration: legacy physical rules -> virtual_overrides (inverted)
        // This runs only when the editor has discovered the port list for the selected device.
        try {
          if (!this._didVirtualMigrate) {
            const hasLegacyPref = String(c.physical_prefixes || "").trim();
            const hasLegacyRx = String(c.physical_regex || "").trim();
            const hasLegacy = !!(hasLegacyPref || hasLegacyRx);
            const hasVirtualOverrides = Array.isArray(c.virtual_overrides)
              ? c.virtual_overrides.length > 0
              : (typeof c.virtual_overrides === "string" && c.virtual_overrides.trim());
            if (hasLegacy && !hasVirtualOverrides && portChoices.length) {
              const rxStr = hasLegacyRx;
              const prefStr = hasLegacyPref;
              const prefs = prefStr ? prefStr.split(",").map(s=>s.trim()).filter(Boolean) : [];
              let rx = null;
              if (rxStr) {
                try { rx = new RegExp(rxStr, "i"); } catch(e) { rx = null; }
              }
              const virtualNames = [];
              for (const p of portChoices) {
                const n = String(p.name || "").trim();
                const id = String(p.entity_id || "").trim();
                if (!n && !id) continue;
                let isPhysical = false;
                if (rx) isPhysical = rx.test(n) || rx.test(id);
                if (!isPhysical && !rx && prefs.length) {
                  const nUp = n.toUpperCase();
                  isPhysical = prefs.some(pp => nUp.startsWith(String(pp).trim().toUpperCase()));
                }
                // If legacy rules match physical, virtual is the inverse.
                if (!isPhysical && n) virtualNames.push(n);
              }
              // De-dupe (case-insensitive) while preserving order
              const seen = new Set();
              const virtDedup = [];
              for (const v of virtualNames) {
                const k = String(v).toLowerCase();
                if (seen.has(k)) continue;
                seen.add(k);
                virtDedup.push(v);
              }
              const newConfig = { ...this._config, virtual_overrides: virtDedup };
              // Remove legacy keys from config so they don't keep surfacing in UI/logic
              delete newConfig.physical_prefixes;
              delete newConfig.physical_regex;
              this._config = newConfig;
              this._didVirtualMigrate = true;
              this.dispatchEvent(new CustomEvent("config-changed", {
                detail: { config: newConfig },
                bubbles: true,
                composed: true,
              }));
              // Continue render using migrated config
              c = newConfig;
            }
          }
        } catch(e) {}

        const normLower = (arr) => {
          const out = [];
          const seen = new Set();
          (arr || []).forEach(v => {
            const s = String(v || "").trim();
            if (!s) return;
            const k = s.toLowerCase();
            if (seen.has(k)) return;
            seen.add(k);
            out.push(s);
          });
          return out;
        };
        const _alphaSort = (arr) => (arr || []).slice().sort(_ssmNaturalPortCompare);
        const hidePortsArr = _alphaSort(normLower(c.hide_ports));
        const uplinkPortsArr = _alphaSort(normLower(c.uplink_ports));
        const virtualOverridesArr = _alphaSort(normLower(c.virtual_overrides));

        const portDatalistHtml = portNameChoices.length
          ? portNameChoices.slice().sort((a,b)=>_ssmNaturalPortCompare(a,b)).map(n => `<option value="${this._escape(n)}"></option>`).join("")
          : "";

        const renderSelectList = (arr, kind) => {
          if (!arr.length) return ``;
    const sorted = [...arr].sort((a, b) => _ssmNaturalPortCompare(a, b));
  // Render as HA-style selectable list rows (not chips) for consistency with current HA editors.
  // We still use data-chip-* attrs so existing remove handlers keep working.
  return `<div class="halist" id="${kind}_list">` + sorted.map(v =>
    `<div class="halist-row">
      <div class="halist-main">
        <div class="halist-title">${this._escape(v)}</div>
      </div>
      <button type="button" class="halist-remove chip" data-chip-kind="${kind}" data-chip-val="${this._escape(v)}" title="Remove">×</button>
    </div>`
  ).join("") + `</div>`;
};

        const hidePortsHtml = `
          ${renderSelectList(hidePortsArr, "hide_ports")}
          <div class="chipadd">
            <input id="hide_ports_add" class="chipinput" type="text" list="ssm_ports_datalist" placeholder="Add port…">
            <button type="button" class="chipbtn" id="hide_ports_add_btn">Add</button>
          </div>
        `;

        const uplinkPortsHtml = `
          ${renderSelectList(uplinkPortsArr, "uplink_ports")}
          <div class="chipadd">
            <input id="uplink_ports_add" class="chipinput" type="text" list="ssm_ports_datalist" placeholder="Add uplink port…">
            <button type="button" class="chipbtn" id="uplink_ports_add_btn">Add</button>
          </div>
        `;

        const virtualOverridesHtml = `
          ${renderSelectList(virtualOverridesArr, "virtual_overrides")}
          <div class="chipadd">
            <input id="virtual_overrides_add" class="chipinput" type="text" list="ssm_ports_datalist" placeholder="Add virtual interface…">
            <button type="button" class="chipbtn" id="virtual_overrides_add_btn">Add</button>
          </div>
        `;

        const stateColorsHtml = (c.color_mode === "speed") ? "" : this._renderStateColorsSection(c);
        const speedColorsHtml = (c.color_mode === "speed") ? this._renderSpeedColorsSection(c) : "";

        this.shadowRoot.innerHTML = `
          <style>
            .form{display:flex;flex-direction:column;gap:12px;padding:8px 4px 12px;}
            details.section{border:1px solid var(--divider-color);border-radius:14px;background:var(--card-background-color);overflow:hidden;}
            details.section + details.section{margin-top:12px;}
            details.section > summary{list-style:none;cursor:pointer;padding:12px 14px;font-size:14px;font-weight:600;display:flex;align-items:center;justify-content:space-between;}
            details.section > summary::-webkit-details-marker{display:none;}
details.section > summary::after{
              content:"▾";
              font-size:18px;
              opacity:0.75;
              transition: transform .18s ease;
            }
            details.section[open] > summary::after{
              transform: rotate(180deg);
            }
            details.section[open] > summary{border-bottom:1px solid var(--divider-color);}
            .secbody{padding:12px 14px;display:flex;flex-direction:column;gap:12px;}
            .row{display:flex;flex-direction:column;gap:4px;}
            .row.inline{flex-direction:row;align-items:center;justify-content:space-between;gap:10px;}
            .row.two{display:grid;grid-template-columns:1fr 1fr;gap:12px;align-items:end;}
            /* Dark dropdowns (fix white background in HA dialogs) */
            select, option {
              color: var(--primary-text-color);
            }
            select {
              background: var(--card-background-color);
              border: 1px solid var(--divider-color);
              border-radius: 10px;
              padding: 10px 12px;
              color-scheme: dark;
            }
            option { background: var(--card-background-color); }
            
            .diaglist{display:flex;flex-direction:column;gap:8px;}
            .diagitem{display:flex;align-items:center;justify-content:space-between;gap:10px;
              padding:10px 12px;border:1px solid var(--divider-color);border-radius:12px;
              background:rgba(0,0,0,0.10);cursor:pointer;}
            .diagitem.disabled{opacity:0.55;}
            .diagname{font-weight:600; overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
            .diagactions{display:flex;align-items:center;gap:8px;}
            .btn.icon{width:34px; padding:0; text-align:center;}
            .sub{font-size:12px; opacity:0.85;}

            /* Compact color grids */
            .colorGrid{
              display:grid;
              grid-template-columns: repeat(auto-fill, minmax(95px, 1fr));
              gap:10px;
              align-items:start;
            }
            .colorItem{
              display:flex;
              flex-direction:column;
              gap:6px;
              padding:8px;
              border:1px solid var(--divider-color);
              border-radius:12px;
              background:rgba(0,0,0,0.06);
            }
            .colorControls{display:flex;flex-direction:column;align-items:stretch;justify-content:flex-start;gap:8px;}
            .colorTitle{
              font-size:12px;
              font-weight:600;
              opacity:0.95;
              text-align:left;
              white-space:nowrap;
              overflow:hidden;
              text-overflow:ellipsis;
            }
            .statecolor,.speedcolor{width:34px;height:34px;padding:0;border:none;background:transparent;border-radius:8px;margin:0 auto;display:block;}
            .statehex,.speedhex{width:100%;max-width:none;font-family:var(--code-font-family, monospace);padding:6px 8px;border-radius:10px;border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color);text-align:center;box-sizing:border-box;}

            .hint{display:none;}
            .subhead-row{display:flex; align-items:center; justify-content:space-between; gap:10px;}
      .rowhead{position:relative;display:flex;align-items:center;justify-content:space-between;gap:8px;}
      .rowhead label{margin:0;}
      .helpiconbtn{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:999px;background:transparent;border:1px solid var(--divider-color);color:var(--secondary-text-color);cursor:pointer;flex:0 0 auto;}
      /* Nudge the icon up slightly so it visually aligns with the label baseline */
      .rowhead .helpiconbtn{transform:translateY(-1px);}
.helpiconbtn:hover{background:rgba(0,0,0,0.18);} 
.helpiconbtn:active{background:rgba(0,0,0,0.26);} 
.helpiconbtn:focus{outline:2px solid var(--primary-color);outline-offset:2px;}
.helpiconbtn ha-icon{--mdc-icon-size:18px;}

.ssm-help-popover{position:fixed; z-index:99999; max-width:340px; padding:10px 12px; border-radius:12px; border:1px solid var(--divider-color); background:var(--card-background-color); color:var(--primary-text-color); box-shadow:0 10px 30px rgba(0,0,0,.45); font-size:13px; line-height:1.35;}
      .ssm-help-popover .close:hover{background:rgba(0,0,0,0.15);} 
.helpline{display:flex;justify-content:flex-end;margin-top:6px;}
            label{font-size:13px;font-weight:500;}
            input[type="text"],input[type="number"],select,textarea{width:100%;box-sizing:border-box;padding:9px 10px;border-radius:10px;border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color);}input[type="text"]:focus,input[type="number"]:focus,select:focus,textarea:focus{outline:2px solid var(--primary-color);outline-offset:2px;}
            textarea{min-height:72px;resize:vertical;}
            .inline{display:flex;gap:8px;align-items:center;}
            .btn{padding:8px 12px;border-radius:10px;border:1px solid var(--divider-color);background:var(--card-background-color);cursor:pointer;}
            .iconbtn{width:36px;height:36px;border-radius:10px;border:1px solid var(--divider-color);background:var(--card-background-color);cursor:pointer;display:flex;align-items:center;justify-content:center;padding:0;}
            .iconbtn.sm{width:32px;height:32px;border-radius:10px;}
            .iconbtn ha-icon{--mdc-icon-size:18px;}
            .iconbtn:disabled{opacity:0.5;cursor:default;}

            .btn.sm{padding:4px 10px;border-radius:10px;font-size:12px;}
            .divider{border-top:1px solid var(--divider-color);margin:8px 0;}
            /* searchable checklist */
            .pickwrap{display:flex;flex-direction:column;gap:8px;}
            .picksearch{width:100%;}
            .picklist{border:1px solid var(--divider-color);border-radius:10px;padding:8px;max-height:220px;overflow:auto;display:flex;flex-direction:column;gap:6px;background:rgba(0,0,0,0.02);}
            .chk{display:flex;gap:8px;align-items:center;font-size:13px;}

            /* HA-style selectable lists (used for Hide ports / Uplink ports / Physical prefixes) */
.halist{border:1px solid var(--divider-color);border-radius:14px;overflow:hidden;background:rgba(0,0,0,0.03);}
.halist-row{display:flex;align-items:center;gap:10px;padding:10px 12px;border-bottom:1px solid var(--divider-color);}
.halist-row:last-child{border-bottom:none;}
.halist-main{flex:1;min-width:0;}
.halist-title{font-size:14px;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.halist-remove{width:34px;height:34px;border-radius:10px;border:1px solid var(--divider-color);background:rgba(0,0,0,0.02);color:var(--primary-text-color);cursor:pointer;font-size:18px;line-height:1;display:flex;align-items:center;justify-content:center;}
.halist-remove:hover{background:rgba(0,0,0,0.06);}

/* add row under lists */
.chipadd{margin-top:10px;display:flex;gap:10px;align-items:center;}
.chipinput{flex:1;min-width:0;padding:9px 10px;border-radius:10px;border:1px solid var(--divider-color);background:rgba(0,0,0,0.02);color:var(--primary-text-color);}
.chipbtn{padding:9px 12px;border-radius:10px;border:1px solid var(--divider-color);background:rgba(0,0,0,0.02);color:var(--primary-text-color);cursor:pointer;}
.chipbtn:hover{background:rgba(0,0,0,0.06);}
            .chip .x{font-size:14px;line-height:1;opacity:.75;margin-left:2px;}
            .chipadd{display:flex;gap:8px;align-items:center;margin-top:8px;}
            .chipinput{flex:1;min-width:120px;}
            .chipbtn{border:1px solid var(--divider-color);border-radius:10px;padding:6px 10px;background:var(--card-background-color);cursor:pointer;}
            .chipbtn:hover{background:rgba(0,0,0,0.04);}
            .diaglist{display:flex;flex-direction:column;gap:6px;width:100%;}
            .diagitem{display:flex;align-items:center;justify-content:space-between;border:1px solid var(--divider-color);border-radius:10px;padding:6px 8px;}
            .diagbtns{display:flex;gap:6px;}
            .diagbtns button{cursor:pointer;padding:2px 8px;border:1px solid var(--divider-color);border-radius:10px;background:var(--card-background-color);color:var(--primary-text-color);}
          </style>

          <div class="form">

            <datalist id="ssm_ports_datalist">
              ${portDatalistHtml}
            </datalist>

            <details class="section" open>
              <summary>Switch</summary>
              <div class="secbody">
                <div class="row">
                  <label for="title">Title</label>
                  <input id="title" type="text" value="${this._escape(((this._draftTitle ?? c.title) || ""))}">
                </div>

                <div class="row">
                  <label for="device">Switch device</label>
                  <select id="device">
                    <option value="">Select a device…</option>
                    ${deviceOptions}
                  </select>
                  <div class="hint">Select a SNMP Switch Manager device (derived from entity ID prefixes).</div>
                </div>
              </div>
            </details>

            <details class="section" open>
              <summary>Layout</summary>
              <div class="secbody">
                <div class="row two">
                  <div class="row">
                    <label for="view">View</label>
                    <select id="view">
                      <option value="panel"${c.view === "panel" ? " selected" : ""}>Panel</option>
                      <option value="list"${c.view === "list" ? " selected" : ""}>List</option>
                    </select>
                  </div>
                  <div class="row">
                    <label for="info_position">Info position</label>
                    <select id="info_position">
                      <option value="above"${c.info_position !== "below" ? " selected" : ""}>Above ports</option>
                      <option value="below"${c.info_position === "below" ? " selected" : ""}>Below ports</option>
                    </select>
                  </div>

                </div>${c.view === "panel" ? `

                <div class="row">
                  <label for="background_image">Panel background image (optional)</label>
                  <input id="background_image" type="text" placeholder="/local/your_switch.png" value="${c.background_image != null ? this._escape(c.background_image) : ""}">
                  <div class="hint">Only used in Panel view.</div>
                ` : ""}
</div>${c.view === "panel" ? `

                <div class="row inline">
                  <label for="calibration_mode">Layout Editor</label><div class="helpiconbtn" data-help-title="Layout Editor" data-help="layout_editor"><ha-icon icon="mdi:help-circle-outline"></ha-icon></div>
                  <ha-switch id="calibration_mode" ${c.calibration_mode ? " checked" : ""}${c.view === "list" ? " disabled" : ""}></ha-switch>
                </div>
                ` : ""}
<div class="row two">${c.view === "panel" ? `
                  <div class="row">
                    <div class="rowhead"><label for="ports_per_row">Ports per row</label><div class="helpiconbtn" data-help-title="Ports per row" data-help="ports_per_row"><ha-icon icon="mdi:help-circle-outline"></ha-icon></div></div>
                    <input id="ports_per_row" type="number" min="1" value="${(this._editingFields?.has('ports_per_row') && this._draftValues?.ports_per_row != null) ? this._draftValues.ports_per_row : (c.ports_per_row != null ? Number(c.ports_per_row) : 24)}"${c.view === "list" ? " disabled" : ""}>
                  </div>
                  <div class="row">
                    <div class="rowhead"><label for="panel_width">Panel width</label><div class="helpiconbtn" data-help-title="Panel width" data-help="panel_width"><ha-icon icon="mdi:help-circle-outline"></ha-icon></div></div>
                    <input id="panel_width" type="number" min="0" value="${(this._editingFields?.has('panel_width') && this._draftValues?.panel_width != null) ? this._draftValues.panel_width : (c.panel_width != null ? Number(c.panel_width) : 740)}"${c.view === "list" ? " disabled" : ""}>
                  </div>
                ` : ""}</div>

                <div class="row">${c.view === "panel" ? `
                  <div class="rowhead"><label for="port_scale">Port scale</label><div class="helpiconbtn" data-help-title="Port scale" data-help="port_scale"><ha-icon icon="mdi:help-circle-outline"></ha-icon></div></div>
                  <input id="port_scale" type="number" step="0.05" min="0" value="${c.port_scale != null ? Number(c.port_scale) : 1}"${c.view === "list" ? " disabled" : ""}>
                ` : ""}</div>

                <div class="row two">${c.view === "panel" ? `
                  <div class="row">
                    <div class="rowhead">
                      <label for="horizontal_port_gap">Horizontal port gap</label>
                      <div class="helpiconbtn" data-help-title="Horizontal port gap" data-help="horizontal_port_gap"><ha-icon icon="mdi:help-circle-outline"></ha-icon></div>
                    </div>
                    <input id="horizontal_port_gap" type="number" min="0" value="${(this._draftValues?.horizontal_port_gap != null) ? this._draftValues.horizontal_port_gap : (c.horizontal_port_gap != null ? Number(c.horizontal_port_gap) : 10)}"${c.view === "list" ? " disabled" : ""}>
                  </div>
                  <div class="row">
                    <div class="rowhead">
                      <label for="vertical_port_gap">Vertical port gap</label>
                      <div class="helpiconbtn" data-help-title="Vertical port gap" data-help="vertical_port_gap"><ha-icon icon="mdi:help-circle-outline"></ha-icon></div>
                    </div>
                    <input id="vertical_port_gap" type="number" min="0" value="${(this._draftValues?.vertical_port_gap != null) ? this._draftValues.vertical_port_gap : (c.vertical_port_gap != null ? Number(c.vertical_port_gap) : 10)}"${c.view === "list" ? " disabled" : ""}>
                  </div>
                ` : ""}</div>

              </div>
            </details>

            <details class="section" open>
              <summary>Appearance</summary>
              <div class="secbody">

                <div class="row">
                  <label for="color_mode">Port colors</label>
                  <select id="color_mode">
                    <option value="state"${(c.color_mode !== "speed") ? " selected" : ""}>State (Admin/Oper)</option>
                    <option value="speed"${(c.color_mode === "speed") ? " selected" : ""}>Speed</option>
                  </select>
                  <div class="hint">Choose whether port colors represent port state or link speed.</div>
                  ${stateColorsHtml}${speedColorsHtml}
                </div>${_hasBandwidth ? `

                <div class="row inline">
                  <div class="rowhead">
                    <label for="speed_click_opens_graph">Open traffic graph on port click</label>
                    <div class="helpiconbtn" icon="mdi:help-circle-outline" data-help-title="Open traffic graph on port click" data-help="speed_click_opens_graph"><ha-icon icon="mdi:help-circle-outline"></ha-icon></div>
                  </div>
                  <ha-switch id="speed_click_opens_graph" ${c.speed_click_opens_graph ? " checked" : ""}></ha-switch>
                </div>

                ` : ""}${c.view === "panel" ? `

                <div class="row inline" style="gap:10px; align-items:center;">
  <label for="show_labels" style="flex:1 1 auto;">Show port labels</label>
  <select id="label_position" style="width:160px; margin-right:6px;"
    ${c.show_labels === false || c.view === "list" ? " disabled" : ""}>
    <option value="below"${(c.label_position || "below") === "below" ? " selected" : ""}>Below</option>
    <option value="above"${(c.label_position || "below") === "above" ? " selected" : ""}>Above</option>
    <option value="inside"${(c.label_position || "below") === "inside" ? " selected" : ""}>Inside</option>
    <option value="split"${(c.label_position || "below") === "split" ? " selected" : ""}>Split (2 row)</option>
  </select>
  <div class="helpiconbtn" data-help-title="Label position" data-help="label_position"><ha-icon icon="mdi:help-circle-outline"></ha-icon></div>
  <ha-switch id="show_labels" ${c.show_labels !== false ? "checked" : ""}${c.view === "list" ? " disabled" : ""}></ha-switch>
</div>
` : ""}${c.view === "panel" ? `
<div class="row inline">
                  <label for="label_numbers_only">Labels: numbers only</label>
                  <ha-switch id="label_numbers_only" ${c.label_numbers_only ? " checked" : ""}${c.show_labels === false || c.view === "list" ? " disabled" : ""}></ha-switch>
                </div>



<div class="row inline" style="gap:10px; align-items:center;">
  <div class="rowhead" style="display:flex; align-items:center; justify-content:flex-start; gap:6px; flex:1 1 auto;">
    <label for="label_numbers_from" style="margin:0;">Numbers from</label>
    <div class="helpiconbtn" data-help-title="Numbers from" data-help="label_numbers_from"><ha-icon icon="mdi:help-circle-outline"></ha-icon></div>
  </div>
  <select id="label_numbers_from" style="width:160px; margin-right:6px;"${c.show_labels === false || c.view === "list" || c.label_numbers_only !== true ? " disabled" : ""}>
    <option value="index"${(c.label_numbers_from !== "port_name") ? " selected" : ""}>Index</option>
    <option value="port_name"${(c.label_numbers_from === "port_name") ? " selected" : ""}>Port name</option>
  </select>
  <!-- spacer to keep this dropdown aligned with the row above (which has help+switch on the right) -->
  <div style="width:82px;"></div>
</div>
<div class="row inline" style="gap:10px; align-items:center;">
  <div class="rowhead" style="display:flex; align-items:center; gap:6px; flex:1 1 auto;">
    <label for="label_outline" style="margin:0;">Outline port labels</label>
    <div class="helpiconbtn" data-help-title="Outline port labels" data-help="label_outline"><ha-icon icon="mdi:help-circle-outline"></ha-icon></div>
  </div>
  <ha-switch id="label_outline"${c.label_outline ? " checked" : ""}${c.show_labels === false || c.view === "list" ? " disabled" : ""}></ha-switch>
</div>
` : ""}${c.view === "panel" ? `
<div class="row">
                  <label for="label_size">Label font size</label>
                  <input id="label_size" type="number" min="0" value="${c.label_size != null ? Number(c.label_size) : 8}"${c.view === "list" ? " disabled" : ""}>
                </div>

                
                ` : ""}${c.view === "panel" ? `
<div class="row two">
                  <div class="row">
                    <label for="label_color">Label font color</label>
                    <div class="inline">
                      <input id="label_color" type="color" value="${c.label_color != null ? String(c.label_color) : "#ffffff"}">
                      <button class="btn sm" id="label_color_clear" type="button" title="Use default label color">Clear</button>
                    </div>
                    <div class="hint">Clear restores the default theme color.</div>
                  </div>

                  ` : ""}
${c.view === "panel" ? `
<div class="row">
                    <label for="label_bg_color">Label background color</label>
                    <div class="inline">
                      <input id="label_bg_color" type="color" value="${c.label_bg_color != null ? String(c.label_bg_color) : "#000000"}">
                      <button class="btn sm" id="label_bg_color_clear" type="button" title="Use default label background color">Clear</button>
                    </div>

` : ""}                    <div class="hint">Clear restores the default background.</div>
                  </div>
                </div>


              </div>
            </details>

            
            <details class="section" open>
              <summary>Content</summary>
              <div class="secbody">

                <div class="row inline">
                  <label for="show_diagnostics">Show Diagnostics</label><div class="helpiconbtn" icon="mdi:help-circle-outline" data-help-title="Show Diagnostics" data-help="show_diagnostics"><ha-icon icon="mdi:help-circle-outline"></ha-icon></div>
                  <ha-switch id="show_diagnostics" ${c.hide_diagnostics ? "" : " checked"}></ha-switch>
                </div>

                ${c.hide_diagnostics ? "" : `
                  <div class="row">
                    <div class="rowhead"><label>Diagnostics order</label><div class="helpiconbtn" icon="mdi:help-circle-outline" data-help-title="Diagnostics order" data-help="diagnostics_order"><ha-icon icon="mdi:help-circle-outline"></ha-icon></div></div>
                    <div class="diaglist">
                      ${(() => {
                        const rawOrder = Array.isArray(c.diagnostics_order) && c.diagnostics_order.length
                          ? c.diagnostics_order
                          : ["hostname","manufacturer","model","firmware_revision","uptime"];
                        const enabledMap = (c.diagnostics_enabled && typeof c.diagnostics_enabled === "object") ? c.diagnostics_enabled : {};
                        const order = rawOrder;
                        return order.map((key, idx) => {
                          const enabled = enabledMap[key] !== false;
                          const label = this._diagnosticLabel(key);
                          const isCustom = key.includes(".");
                          return `
                            <div class="diagitem ${enabled ? "" : "disabled"}" data-diag="${this._escape(key)}">
                              <div class="diagname" title="${this._escape(label)}">${this._escape(label)}</div>
                              <div class="diagactions">
                                <button class="btn icon sm diag-up" data-diag="${this._escape(key)}" title="Move up" ${idx===0?'disabled':''}>▲</button>
                                <button class="btn icon sm diag-down" data-diag="${this._escape(key)}" title="Move down" ${idx===order.length-1?'disabled':''}>▼</button>
                                ${isCustom ? `<button class="btn icon sm diag-remove" data-diag="${this._escape(key)}" title="Remove">✕</button>` : ``}
                              </div>
                            </div>
                          `;
                        }).join("");
                      })()}
                    </div>

                    <div class="row">
                      <label for="diag_add_input" class="sub">Add diagnostic sensor</label>
                      <div class="inline">
                        <input id="diag_add_input" type="text" placeholder="sensor.some_sensor" list="diag_sensors">
                        <button class="btn sm" id="diag_add_btn" type="button">Add</button>
                      </div>
                      <datalist id="diag_sensors">
                        ${this._hass ? Object.keys(this._hass.states).filter(e=>e.startsWith("sensor.")).map(e=>`<option value="${e}"></option>`).join("") : ""}
                      </datalist>
                      <div class="hint">Click a row to enable/disable. Built-in items can be reordered; custom sensors can also be removed.</div>
                    </div>
                  </div>
                `}

                <div class="row inline">
                  <label for="show_virtual_interfaces">Show Virtual Interfaces</label><div class="helpiconbtn" icon="mdi:help-circle-outline" data-help-title="Show Virtual Interfaces" data-help="show_virtual"><ha-icon icon="mdi:help-circle-outline"></ha-icon></div>
                  <ha-switch id="show_virtual_interfaces" ${c.hide_virtual_interfaces ? "" : " checked"}></ha-switch>
                </div>

                <div class="row inline">
                  <label for="hide_control_buttons">Hide control buttons</label><div class="helpiconbtn" icon="mdi:help-circle-outline" data-help-title="Hide control buttons" data-help="hide_controls"><ha-icon icon="mdi:help-circle-outline"></ha-icon></div>
                  <ha-switch id="hide_control_buttons" ${c.hide_control_buttons ? " checked" : ""}></ha-switch>
                </div>

                ${c.hide_virtual_interfaces ? "" : `
                  <div class="row">
                    <div class="rowhead"><label>Virtual interfaces (override)</label><div class="helpiconbtn" icon="mdi:help-circle-outline" data-help-title="Virtual interfaces (override)" data-help="virtual_overrides"><ha-icon icon="mdi:help-circle-outline"></ha-icon></div></div>
                  </div>

                  ${virtualOverridesHtml}
                `}

                <div class="divider"></div>

                <div class="row inline">
                  <label for="show_uplinks_separately">Show uplinks separately in layout</label><div class="helpiconbtn" icon="mdi:help-circle-outline" data-help-title="Show uplinks separately in layout" data-help="show_uplinks_separately"><ha-icon icon="mdi:help-circle-outline"></ha-icon></div>
                  <ha-switch id="show_uplinks_separately" ${c.show_uplinks_separately ? " checked" : ""}></ha-switch>
                </div>

                ${c.show_uplinks_separately ? `
                  <div class="row">
                    <div class="rowhead"><label>Uplink ports</label><div class="helpiconbtn" icon="mdi:help-circle-outline" data-help-title="Uplink ports" data-help="uplink_ports"><ha-icon icon="mdi:help-circle-outline"></ha-icon></div></div>
                    ${uplinkPortsHtml}
                  </div>
                ` : ""}

                <div class="divider"></div>
<div class="divider"></div>

                <div class="row">
                  <div class="rowhead"><label>Hide ports</label><div class="helpiconbtn" icon="mdi:help-circle-outline" data-help-title="Hide ports" data-help="hide_ports"><ha-icon icon="mdi:help-circle-outline"></ha-icon></div></div>
                          ${hidePortsHtml}
                </div>

              </div>
            </details>

          </div>
        `;

        const root = this.shadowRoot;

        // Ensure HA icons render inside the editor
        root.querySelectorAll("ha-icon").forEach((el) => { try { el.hass = this._hass; } catch (e) {} });

        // Title (use draft value to prevent re-render on every keystroke)
        const titleEl = root.getElementById("title");
        titleEl?.addEventListener("focus", () => {
          this._editingTitle = true;
          // Initialize draft from current config once the user starts editing.
          if (this._draftTitle === null || this._draftTitle === undefined) {
            this._draftTitle = this._config?.title ?? "";
          }
        });
        titleEl?.addEventListener("input", (ev) => {
          this._draftTitle = ev.target.value;
        });
        const commitTitle = () => {
          const next = (this._draftTitle ?? "").toString();
          const cur = (this._config?.title ?? "").toString();
          this._editingTitle = false;
          if (next !== cur) this._updateConfig("title", next);
          // Keep draft in sync with committed value.
          this._draftTitle = null;
        };
        titleEl?.addEventListener("blur", commitTitle);
        titleEl?.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter") {
            ev.preventDefault();
            titleEl.blur();
          }
          if (ev.key === "Escape") {
            // Revert draft and stop editing.
            this._draftTitle = null;
            this._editingTitle = false;
            this._rendered = false;
            this._render();
          }
        });

// Switch device
root.getElementById("device")?.addEventListener("change", (ev) => {
  const next = (ev.target.value || "").toString();
  this._updateConfig("device", next);
  // Force port list + datalist to refresh for the new device.
  this._lastPortsSig = "";
  this._render();
});

        // View
        root.getElementById("view")?.addEventListener("change", (ev) => {
          this._updateConfig("view", ev.target.value || "panel");
        });

        // Panel layout basics (only relevant in panel view)
        root.getElementById("ports_per_row")?.addEventListener("change", (ev) => {
          const v = parseInt(ev.target.value, 10);
          this._updateConfig("ports_per_row", (Number.isFinite(v) && v > 0) ? v : 24);
        });
        root.getElementById("panel_width")?.addEventListener("change", (ev) => {
          const v = parseInt(ev.target.value, 10);
          this._updateConfig("panel_width", (Number.isFinite(v) && v >= 0) ? v : 740);
        });
        // Drafted number inputs (avoid HA editor re-renders clobbering typing)
        const bindDraftNumber = (id, key, fallback, parseFn) => {
          const el = root.getElementById(id);
          if (!el) return;
          let committed = false;

          const commit = () => {
            if (committed) return;
            committed = true;
            this._editingFields?.delete(key);
            const raw = (this._draftValues && this._draftValues[key] != null) ? this._draftValues[key] : el.value;
            try { if (this._draftValues) delete this._draftValues[key]; } catch (e) {}
            const parsed = (parseFn ? parseFn(raw) : parseInt(raw, 10));
            const v = Number.isFinite(parsed) ? parsed : fallback;
            this._updateConfig(key, v);
            // allow next edit cycle
            setTimeout(() => { committed = false; }, 0);
          };

          el.addEventListener("focus", () => {
            this._editingFields?.add(key);
            if (this._draftValues && this._draftValues[key] == null) this._draftValues[key] = String(el.value ?? "");
          });
          el.addEventListener("input", () => {
            if (this._draftValues) this._draftValues[key] = String(el.value ?? "");
          });
          el.addEventListener("blur", commit);
          el.addEventListener("change", commit);
        };

        bindDraftNumber("ports_per_row", "ports_per_row", 24, (raw) => {
          const n = parseInt(String(raw ?? "").trim(), 10);
          return Number.isFinite(n) && n >= 1 ? n : 24;
        });
        bindDraftNumber("panel_width", "panel_width", 740, (raw) => {
          const n = parseInt(String(raw ?? "").trim(), 10);
          return Number.isFinite(n) && n >= 0 ? n : 740;
        });
        bindDraftNumber("gap", "gap", 10, (raw) => {
          const n = parseInt(String(raw ?? "").trim(), 10);
          return Number.isFinite(n) && n >= 0 ? n : 10;
        });



        // Info position
        root.getElementById("info_position")?.addEventListener("change", (ev) => {
          this._updateConfig(
            "info_position",
            ev.target.value === "below" ? "below" : "above",
          );
        });

        // Port colors (state vs speed)
        root.getElementById("color_mode")?.addEventListener("change", (ev) => {
          const v = String(ev.target.value || "state");
          this._updateConfig("color_mode", v === "speed" ? "speed" : "state");
        });

        root.getElementById("speed_click_opens_graph")?.addEventListener("change", (ev) => {
          this._updateConfig("speed_click_opens_graph", !!ev.target.checked);
        });

        // Speed colors: show full supported speeds list
        root.getElementById("show_all_speeds")?.addEventListener("change", (ev) => {
          this._updateConfig("show_all_speeds", !!ev.target.checked);
          this._rendered = false;
          this._render();
        });

        // Reset buttons (icon buttons in section headers)
        root.getElementById("speed_reset")?.addEventListener("click", (ev) => {
          ev.preventDefault();
          this._updateConfig("speed_colors", null);
          this._rendered = false;
          this._render();
        });
        root.getElementById("state_reset")?.addEventListener("click", (ev) => {
          ev.preventDefault();
          this._updateConfig("state_colors", null);
          this._rendered = false;
          this._render();
        });

        const speedPalette = this._defaultSpeedPalette();
        const statePalette = this._defaultStatePalette();

        
const updateSpeedColor = (label, color) => {
          const lab = String(label || "").trim() || "Unknown";
          const cval = String(color || "").trim();
          if (!/^#[0-9a-fA-F]{6}$/.test(cval)) return;

          const cur = (this._config?.speed_colors && typeof this._config.speed_colors === "object")
            ? { ...this._config.speed_colors }
            : {};
          const def = speedPalette[lab] || speedPalette["Disconnected"] || speedPalette["Unknown"];

          const isDefault = (String(def || "").toLowerCase() === cval.toLowerCase());

          if (lab === "Disconnected") {
            if (isDefault) {
              delete cur["Disconnected"];
              delete cur["Unknown"];
            } else {
              cur["Disconnected"] = cval;
              cur["Unknown"] = cval;
            }
          } else {
            if (isDefault) delete cur[lab];
            else cur[lab] = cval;
          }

          this._updateConfig("speed_colors", Object.keys(cur).length ? cur : null);
        };

        

        const updateStateColor = (key, color) => {
          const k = String(key || "").trim();
          const cval = String(color || "").trim();
          if (!/^#[0-9a-fA-F]{6}$/.test(cval)) return;

          const cur = (this._config?.state_colors && typeof this._config.state_colors === "object")
            ? { ...this._config.state_colors }
            : {};
          const def = statePalette[k] || "#9ca3af";
          if (cval.toLowerCase() === String(def).toLowerCase()) delete cur[k];
          else cur[k] = cval;

          this._updateConfig("state_colors", Object.keys(cur).length ? cur : null);
        };

        // Live sync: picker -> hex (no config write), commit on change
        root.querySelectorAll("input.speedcolor").forEach((inp) => {
          inp.addEventListener("input", () => {
            const lab = inp.dataset.speed || "Unknown";
            const hex = root.querySelector(`input.speedhex[data-speed="${lab}"]`);
            if (hex) hex.value = inp.value;
          });
          inp.addEventListener("change", () => {
            const lab = inp.dataset.speed || "Unknown";
            updateSpeedColor(lab, inp.value);
          });
        });

        root.querySelectorAll("input.statecolor").forEach((inp) => {
          inp.addEventListener("input", () => {
            const lab = inp.dataset.state || "up_up";
            const hex = root.querySelector(`input.statehex[data-state="${lab}"]`);
            if (hex) hex.value = inp.value;
          });
          inp.addEventListener("change", () => {
            const lab = inp.dataset.state || "up_up";
            updateStateColor(lab, inp.value);
          });
        });

        // Commit hex edits on change (avoid rerender while typing)
        root.querySelectorAll("input.speedhex").forEach((inp) => {
          inp.addEventListener("change", () => {
            const lab = inp.dataset.speed || "Unknown";
            let v = String(inp.value || "").trim();
            if (!v) return;
            if (!v.startsWith("#")) v = `#${v}`;
            if (!/^#[0-9a-fA-F]{6}$/.test(v)) return;
            const color = root.querySelector(`input.speedcolor[data-speed="${lab}"]`);
            if (color) color.value = v;
            updateSpeedColor(lab, v);
          });
        });

        root.querySelectorAll("input.statehex").forEach((inp) => {
          inp.addEventListener("change", () => {
            const lab = inp.dataset.state || "up_up";
            let v = String(inp.value || "").trim();
            if (!v) return;
            if (!v.startsWith("#")) v = `#${v}`;
            if (!/^#[0-9a-fA-F]{6}$/.test(v)) return;
            const color = root.querySelector(`input.statecolor[data-state="${lab}"]`);
            if (color) color.value = v;
            updateStateColor(lab, v);
          });
        });

        // Hide ports checklist
        root.querySelectorAll("input[data-hide-port]")?.forEach((el) => {
          el.addEventListener("change", () => {
            const selected = Array.from(root.querySelectorAll("input[data-hide-port]"))
              .filter(x => x.checked)
              .map(x => String(x.getAttribute("data-hide-port") || "").trim())
              .filter(Boolean);
            this._updateConfig("hide_ports", selected);
          });
        });

        // Uplink ports checklist
        root.querySelectorAll("input[data-uplink-port]")?.forEach((el) => {
          el.addEventListener("change", () => {
            const selected = Array.from(root.querySelectorAll("input[data-uplink-port]"))
              .filter(x => x.checked)
              .map(x => String(x.getAttribute("data-uplink-port") || "").trim())
              .filter(Boolean);
            this._updateConfig("uplink_ports", selected);
          });
        });

        
        // Background image + positioning
        root.getElementById("background_image")?.addEventListener("change", (ev) => {
          const v = String(ev.target.value || "").trim();
          this._updateConfig("background_image", v ? v : null);
        });
        root.getElementById("ports_offset_x")?.addEventListener("change", (ev) => {
          const v = parseFloat(ev.target.value);
          this._updateConfig("ports_offset_x", Number.isFinite(v) ? v : 0);
        });
        root.getElementById("ports_offset_y")?.addEventListener("change", (ev) => {
          const v = parseFloat(ev.target.value);
          this._updateConfig("ports_offset_y", Number.isFinite(v) ? v : 0);
        });
        root.getElementById("port_scale")?.addEventListener("change", (ev) => {
          const v = parseFloat(ev.target.value);
          this._updateConfig("port_scale", (Number.isFinite(v) && v >= 0) ? v : 1);
        });

// Horizontal/Vertical port gap (canonical keys)
root.getElementById("horizontal_port_gap")?.addEventListener("change", (ev) => {
  const v = Number(ev.target.value);
  const next = { ...(this._config || {}) };
  next.horizontal_port_gap = Number.isFinite(v) ? v : 10;
  delete next.gap; delete next.gap_x; delete next.gap_y; delete next.port_gap_x; delete next.port_gap_y;
  this._config = next;
  this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: next } }));
});
root.getElementById("vertical_port_gap")?.addEventListener("change", (ev) => {
  const v = Number(ev.target.value);
  const next = { ...(this._config || {}) };
  next.vertical_port_gap = Number.isFinite(v) ? v : 10;
  delete next.gap; delete next.gap_x; delete next.gap_y; delete next.port_gap_x; delete next.port_gap_y;
  this._config = next;
  this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: next } }));
});
        root.getElementById("port_positions")?.addEventListener("change", (ev) => {
          const raw = String(ev.target.value || "").trim();
          if (!raw) { this._updateConfig("port_positions", null); return; }
          try {
            const obj = JSON.parse(raw);
            this._updateConfig("port_positions", (obj && typeof obj === "object") ? obj : null);
          } catch (e) {
            // Keep the user's text, but don't break the editor; ignore invalid JSON.
          }
        });


        root.getElementById("calibration_mode")?.addEventListener("change", (ev) => {
          this._updateConfig("calibration_mode", !!ev.target.checked);
          if (!ev.target.checked) { this._clearCalibDraftFromStorage(); }
        
          try {
            const prefix = (this._config?.device || "") ? String(this._config.device) : "all";
            localStorage.removeItem(`ssm_calib_force_off:${prefix}`);
          } catch (e) {}
});


        // Content toggles
        // UI uses "Show …" switches, but config stores the inverse for diagnostics/virtual.
        root.getElementById("show_diagnostics")?.addEventListener("change", (ev) => {
          // checked = show
          this._updateConfig("hide_diagnostics", !ev.target.checked);
          this._render();
        });

        root.getElementById("show_virtual_interfaces")?.addEventListener("change", (ev) => {
          this._updateConfig("hide_virtual_interfaces", !ev.target.checked);
          this._render();
        });

        root.getElementById("hide_control_buttons")?.addEventListener("change", (ev) => {
          this._updateConfig("hide_control_buttons", !!ev.target.checked);
          this._render();
        });

        root.getElementById("show_uplinks_separately")?.addEventListener("change", (ev) => {
          this._updateConfig("show_uplinks_separately", !!ev.target.checked);
          this._render();
        });


        // Labels under ports (Panel view)
        root.getElementById("show_labels")?.addEventListener("change", (ev) => {
          this._updateConfig("show_labels", !!ev.target.checked);
        });

        root.getElementById("label_numbers_only")?.addEventListener("change", (ev) => {
  this._updateConfig("label_numbers_only", !!ev.target.checked);
  this._render(); // show/hide dependent fields immediately
});

root.getElementById("label_numbers_from")?.addEventListener("change", (ev) => {
  this._updateConfig("label_numbers_from", String(ev.target.value || "index"));
  // no full re-render needed; labels update during normal redraw
});// Outline port labels (only used when "Port labels by number" is enabled)
root.getElementById("label_outline")?.addEventListener("change", (ev) => {
  this._updateConfig("label_outline", ev.target.checked === true);
});


// Label position
        root.getElementById("label_position")?.addEventListener("change", (ev) => {
          const v = String(ev.target.value || "below");
          const ok = (v === "below" || v === "above" || v === "inside" || v === "split");
          this._updateConfig("label_position", ok ? v : "below");
        });

        // Label size
        root.getElementById("label_size")?.addEventListener("change", (ev) => {
          const v = parseInt(ev.target.value, 10);
          this._updateConfig("label_size", Number.isFinite(v) ? v : 8);
        });

        // Label color
        root.getElementById("label_color")?.addEventListener("change", (ev) => {
          const v = String(ev.target.value || "").trim();
          this._updateConfig("label_color", v || null);
        });

        root.getElementById("label_color_clear")?.addEventListener("click", () => {
          this._updateConfig("label_color", null);
          const inp = root.getElementById("label_color");
          if (inp) inp.value = "#ffffff";
        });

        // Label background color
        root.getElementById("label_bg_color")?.addEventListener("change", (ev) => {
          const v = String(ev.target.value || "").trim();
          this._updateConfig("label_bg_color", v || null);
        });
        root.getElementById("label_bg_color_clear")?.addEventListener("click", () => {
          this._updateConfig("label_bg_color", null);
          const inp = root.getElementById("label_bg_color");
          if (inp) inp.value = "#000000";
        });
        // Diagnostics order (auto-discovered sensors)
        const moveDiag = (from, to) => {
          const def = ["hostname","manufacturer","model","firmware_revision","uptime"];
          const order = Array.isArray(this._config.diagnostics_order) && this._config.diagnostics_order.length
            ? [...this._config.diagnostics_order]
            : [...def];
          if (from < 0 || from >= order.length || to < 0 || to >= order.length) return;
          const [it] = order.splice(from, 1);
          order.splice(to, 0, it);
          this._updateConfig("diagnostics_order", order);
        };
        root.querySelectorAll("button.diagup").forEach((btn) => {
          btn.addEventListener("click", (ev) => {
            ev.preventDefault();
            const idx = Number(btn.dataset.idx);
            if (!Number.isFinite(idx)) return;
            moveDiag(idx, idx - 1);
          });
        });
        root.querySelectorAll("button.diagdown").forEach((btn) => {
          btn.addEventListener("click", (ev) => {
            ev.preventDefault();
            const idx = Number(btn.dataset.idx);
            if (!Number.isFinite(idx)) return;
            moveDiag(idx, idx + 1);
          });
        });

        // Chips: add/remove helpers (Hide ports / Uplink ports)
        const normList = (arr) => {
          const out = [];
          const seen = new Set();
          (arr || []).forEach(v => {
            const s = String(v || "").trim();
            if (!s) return;
            const k = s.toLowerCase();
            if (seen.has(k)) return;
            seen.add(k);
            out.push(s);
          });
          return out;
        };

        const addToList = (key, value) => {
          const v = String(value || "").trim();
          if (!v) return;
          const cur = normList(this._config?.[key]);
          const exists = cur.some(x => x.toLowerCase() === v.toLowerCase());
          const next = exists ? cur : [...cur, v];
                    next.sort((a,b)=>_ssmNaturalPortCompare(a,b));
          if (!exists) this._updateConfig(key, next);
        };

        const removeFromList = (key, value) => {
          const v = String(value || "").trim().toLowerCase();
          if (!v) return;
          const cur = normList(this._config?.[key]);
          const next = cur.filter(x => x.toLowerCase() !== v);
                    next.sort((a,b)=>_ssmNaturalPortCompare(a,b));
          this._updateConfig(key, next);
        };

        const bindChipAdd = (key, inputId, btnId) => {
          const inp = root.getElementById(inputId);
          const btn = root.getElementById(btnId);
          const commit = () => {
            if (!inp) return;
            addToList(key, inp.value);
            inp.value = "";
          };
          inp?.addEventListener("keydown", (e) => {
            if (e.key === "Enter") { e.preventDefault(); commit(); }
          });
          btn?.addEventListener("click", (e) => { e.preventDefault(); commit(); });
          inp?.addEventListener("blur", () => {
            // don't auto-add on blur; keep explicit
          });
        };

        bindChipAdd("hide_ports", "hide_ports_add", "hide_ports_add_btn");
        bindChipAdd("uplink_ports", "uplink_ports_add", "uplink_ports_add_btn");
        bindChipAdd("virtual_overrides", "virtual_overrides_add", "virtual_overrides_add_btn");

        this._ssmConvertHintsToHelp(root);

        const addPrefix = (value) => {
          const v = String(value || "").trim();
          if (!v) return;
          const cur = normList(String(this._config?.physical_prefixes || "").split(","));
          const exists = cur.some(x => x.toLowerCase() === v.toLowerCase());
          const next = exists ? cur : [...cur, v];
                    next.sort((a,b)=>_ssmNaturalPortCompare(a,b));
          if (!exists) this._updateConfig("physical_prefixes", next.join(", "));
        };
        const removePrefix = (value) => {
          const v = String(value || "").trim().toLowerCase();
          if (!v) return;
          const cur = normList(String(this._config?.physical_prefixes || "").split(","));
          const next = cur.filter(x => x.toLowerCase() !== v);
                    next.sort((a,b)=>_ssmNaturalPortCompare(a,b));
          this._updateConfig("physical_prefixes", next.join(", "));
        };

        const bindPrefixAdd = () => {
          const inp = root.getElementById("physical_prefixes_add");
          const btn = root.getElementById("physical_prefixes_add_btn");
          const commit = () => {
            if (!inp) return;
            addPrefix(inp.value);
            inp.value = "";
          };
          inp?.addEventListener("keydown", (e) => {
            if (e.key === "Enter") { e.preventDefault(); commit(); }
          });
          btn?.addEventListener("click", (e) => { e.preventDefault(); commit(); });
        };
        bindPrefixAdd();

        root.querySelectorAll(".chip[data-chip-kind]").forEach((b) => {
          b.addEventListener("click", (e) => {
            e.preventDefault();
            const kind = String(b.dataset.chipKind || "");
            const val = String(b.dataset.chipVal || "");
            if (kind === "hide_ports") removeFromList("hide_ports", val);
            if (kind === "uplink_ports") removeFromList("uplink_ports", val);
            if (kind === "virtual_overrides") removeFromList("virtual_overrides", val);
            if (kind === "physical_prefixes") removePrefix(val);
          });
        });
// Diagnostics order (toggle/reorder/add)
        const diagList = root.querySelector(".diaglist");
        if (diagList) {
          const getDiagOrder = () => {
            const order = Array.isArray(this._config.diagnostics_order) && this._config.diagnostics_order.length
              ? [...this._config.diagnostics_order]
              : ["hostname","manufacturer","model","firmware","uptime"];
            return order;
          };
          const setDiagOrder = (order) => {
            this._updateConfig("diagnostics_order", order);
          };
          const getEnabledMap = () => {
            const m = (this._config.diagnostics_enabled && typeof this._config.diagnostics_enabled === "object")
              ? { ...this._config.diagnostics_enabled }
              : {};
            return m;
          };
          const setEnabledMap = (m) => {
            this._updateConfig("diagnostics_enabled", m);
          };

          const toggleDiag = (key) => {
            const m = getEnabledMap();
            m[key] = m[key] === false ? true : false;
            setEnabledMap(m);
            this._render();
          };

          diagList.addEventListener("click", (ev) => {
            const btn = ev.target.closest("button");
            if (btn) return; // handled below
            const row = ev.target.closest(".diagitem");
            if (!row) return;
            const key = row.getAttribute("data-diag") || "";
            if (key) toggleDiag(key);
          });

          diagList.querySelectorAll("button.diag-up").forEach((b) => {
            b.addEventListener("click", (ev) => {
              const key = ev.currentTarget.getAttribute("data-diag") || "";
              const order = getDiagOrder();
              const i = order.indexOf(key);
              if (i > 0) {
                order.splice(i, 1);
                order.splice(i - 1, 0, key);
                setDiagOrder(order);
                this._render();
              }
              ev.stopPropagation();
            });
          });

          diagList.querySelectorAll("button.diag-down").forEach((b) => {
            b.addEventListener("click", (ev) => {
              const key = ev.currentTarget.getAttribute("data-diag") || "";
              const order = getDiagOrder();
              const i = order.indexOf(key);
              if (i !== -1 && i < order.length - 1) {
                order.splice(i, 1);
                order.splice(i + 1, 0, key);
                setDiagOrder(order);
                this._render();
              }
              ev.stopPropagation();
            });
          });

          diagList.querySelectorAll("button.diag-remove").forEach((b) => {
            b.addEventListener("click", (ev) => {
              const key = ev.currentTarget.getAttribute("data-diag") || "";
              const order = getDiagOrder().filter((x) => x !== key);
              setDiagOrder(order);
              const m = getEnabledMap();
              if (this._isAutoDefaultDiagKey(key)) m[key] = false;
              else delete m[key];
              setEnabledMap(m);
              this._render();
              ev.stopPropagation();
            });
          });

          const addBtn = root.getElementById("diag_add_btn");
          const addInput = root.getElementById("diag_add_input");
          if (addBtn && addInput) {
            addBtn.addEventListener("click", () => {
              const val = String(addInput.value || "").trim();
              if (!val) return;
              const order = getDiagOrder();
              if (!order.includes(val)) order.push(val);
              setDiagOrder(order);
              const m = getEnabledMap();
              m[val] = true;
              setEnabledMap(m);
              addInput.value = "";
              this._render();
            });
          }
        }

        requestAnimationFrame(() => this._applyAutoScale());
        this._rendered = true;
      }
    
  
    _ssmConvertHintsToHelp(root) {
      // 1) Bind explicit help icons we placed in section headers (Virtual/Uplink/Hide).
      const helpText = {
        virtual_overrides:
          "Interfaces listed here are treated as Virtual. All others are treated as Physical. This affects classification even if the Virtual panel is hidden.",
        uplink_ports: "Select uplink ports so they can be placed separately from the main port grid in the layout.",
        hide_ports: "Hidden ports are removed from both Panel and List views.",
      };

      const HELP_TEXTS = {
  // Content
  diagnostics_order: {
    title: "Diagnostics order",
    text: "Controls which Diagnostics rows appear and in what order. Click a row to enable/disable it. Use ▲/▼ to reorder; custom sensors can also be removed."
  },
  show_diagnostics: {
    title: "Show Diagnostics",
    text: "Enable or hide the Diagnostics section on the card. When disabled, diagnostic rows are not shown."
  },
  show_virtual: {
    title: "Show Virtual Interfaces",
    text: "Show or hide the Virtual Interfaces panel. Classification still uses the override list even if the panel is hidden."
  },
  hide_controls: {
    title: "Hide control buttons",
    text: "Hides the Turn on/Turn off buttons in the card (Virtual Interfaces list + port popup). Useful if you want to avoid accidentally toggling ports from the UI."
  },
  show_uplinks_separately: {
    title: "Show uplinks separately in layout",
    text: "When enabled, ports you mark as Uplink ports can be positioned separately in the Layout Editor. This does not change which ports are shown on the card."
  },
  // Layout
  layout_editor: {
    title: "Layout Editor",
    text: "Opens an on-card layout editor so you can drag ports into place. Click Save to persist positions locally. Use the X button to exit the editor."
  },
  ports_per_row: {
    title: "Ports per row",
    text: "Panel view only. Controls how many ports are placed in each row when you are not using custom port positions."
  },
  panel_width: {
    title: "Panel width",
    text: "Panel view only. Sets the width of the panel canvas (in pixels)."
  },
  port_scale: {
    title: "Port scale",
    text: "Panel view only. Scales the size of port squares and labels."
  },
  port_gap: {
    title: "Port gap",
    text: "Panel view only. Spacing between ports when using automatic layout."
  },

  // Lists
  virtual_overrides: {
    title: "Virtual interfaces (override)",
    text: "Interfaces listed here are treated as Virtual. All others are treated as Physical. This affects classification even if the Virtual panel is hidden."
  },
  uplink_ports: {
    title: "Uplink ports",
    text: "Select uplink ports so Ports and Uplinks mode and the Layout Editor can keep them separate from the main port grid (if enabled)."
  },
  uplinks: { // backward-compatible key
    title: "Uplink ports",
    text: "Select uplink ports so Ports and Uplinks mode and the Layout Editor can keep them separate from the main port grid (if enabled)."
  },
  hide_ports: {
    title: "Hide ports",
    text: "Hidden ports are removed from both Panel and List views."
  },

  // Appearance
  label_font_color: {
    title: "Label font color",
    text: "Overrides the label text color for port labels. Use Clear to return to the default."
  },
  label_bg_color: {
    title: "Label background color",
    text: "Optional background behind port labels (Panel view) to improve contrast. Use Clear to remove and return to the default."
  },
  label_position: {
    title: "Label position",
    text: "Choose where the port labels render relative to the port squares. Below = under the port. Above = over the port. Inside = centered inside the port. Split (2 row) = top row labels above and bottom row labels below."
  },

  speed_click_opens_graph: {
    title: "Open traffic graph on port click",
    text: "Only applies when Port colors is set to Speed. When enabled, clicking a port opens the bandwidth traffic graph (if bandwidth sensors exist for that port). If no bandwidth sensors are found, the normal port information popup is shown instead."
  },

label_numbers_from: {
  title: "Numbers from",
  text: "When “Labels: numbers only” is enabled, choose where the number comes from: Index uses the interface index (IfIndex) when available (otherwise it falls back to the displayed order), while Port name extracts the right-most numbers from the port name."
},

label_outline: {
  title: "Outline port labels",
  text: "Adds a black outline around numeric port labels to improve readability on bright backgrounds. This only applies when \"Port labels by number\" is enabled."
},

vertical_port_gap: {
  title: "Vertical port gap",
  text: "Spacing between ports in the panel layout. Horizontal controls left/right spacing; Vertical controls top/bottom spacing. Custom port positions from the Layout Editor override automatic spacing."
},

horizontal_port_gap: {
  title: "Horizontal port gap",
  text: "Spacing between ports in the panel layout. Horizontal controls left/right spacing; Vertical controls top/bottom spacing. Custom port positions from the Layout Editor override automatic spacing."
},
};

const _ensureHelpPopover = (container) => {
  let pop = document.querySelector(".ssm-help-popover");
  if (pop) return pop;

  pop = document.createElement("div");
  pop.className = "ssm-help-popover";
  pop.setAttribute("role", "dialog");
  pop.setAttribute("aria-modal", "false");
  pop.style.position = "fixed";
  pop.style.display = "none";
  pop.innerHTML = `
    <div class="ssm-help-title">
      <div class="ssm-help-title-text"></div>
</div>
    <div class="ssm-help-body"></div>
  `;
  container.appendChild(pop);

  const close = () => {
    pop.style.display = "none";
    pop.removeAttribute("data-open");
  };

  // Click outside to close
  window.addEventListener("pointerdown", (e) => {
    if (pop.style.display === "none") return;
    const t = e.target;
    if (!pop.contains(t) && !t?.closest?.(".helpiconbtn")) close();
  }, { capture: true });

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") close();
  });

  return pop;
};

const _showHelpPopover = (btn, keyOrText, fallbackTitle) => {
  const pop = _ensureHelpPopover(root);

  const entry = HELP_TEXTS[keyOrText];
  const title = (entry?.title || fallbackTitle || "Help").trim();
  const text = (entry?.text || String(keyOrText || "")).trim();

  pop.querySelector(".ssm-help-title-text").textContent = title;
  pop.querySelector(".ssm-help-body").textContent = text;

  // Position near the button
  const r = btn.getBoundingClientRect();
  const pad = 10;
  pop.style.display = "block";
  pop.setAttribute("data-open", "1");

  // Temporarily show to measure
  const pr = pop.getBoundingClientRect();
  let left = Math.min(window.innerWidth - pr.width - pad, Math.max(pad, r.left));
  let top = r.bottom + 8;
  if (top + pr.height + pad > window.innerHeight) {
    top = Math.max(pad, r.top - pr.height - 8);
  }
  pop.style.left = `${left}px`;
  pop.style.top = `${top}px`;
};

const bindPopover = (btn, keyOrText, title) => {
  // Make click target less fiddly: larger, always clickable
  btn.style.cursor = "pointer";
  btn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    _showHelpPopover(btn, keyOrText, title);
  }, { passive: false });
};
      root.querySelectorAll(".helpiconbtn[data-help]").forEach((btn) => {
        const key = btn.getAttribute("data-help") || "";
        bindPopover(btn, key || "", (btn.getAttribute("data-help-title")||"Help"));

        // Hover tooltip should show the *help text*, not just the title.
        const entry = HELP_TEXTS[key];
        const tip = (entry?.text || entry?.title || key || "Help").trim();
        if (tip) btn.setAttribute("title", tip);
      });

      // 2) Back-compat: convert remaining inline hint blocks into hover/click help icons.
      const hints = root.querySelectorAll(".hint");
    hints.forEach((h) => {
      const text = (h.textContent || "").trim();
      const row = h.closest(".row");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "helpiconbtn";
      btn.setAttribute("aria-label", "Help");
      btn.innerHTML = `<ha-icon icon="mdi:help-circle-outline"></ha-icon>`;
      bindPopover(btn, text, (row?.querySelector("label")?.textContent || "Help").trim() || "Help");

      // Prefer placing the icon on the same line as the field title.
      if (row) {
        let rowhead = row.querySelector(":scope > .rowhead");
        if (!rowhead) {
          const firstLabel = row.querySelector(":scope > label");
          if (firstLabel) {
            rowhead = document.createElement("div");
            rowhead.className = "rowhead";
            // Move the label into the rowhead so the icon aligns right.
            row.insertBefore(rowhead, firstLabel);
            rowhead.appendChild(firstLabel);
          }
        }
        if (rowhead) {
          rowhead.appendChild(btn);
          h.remove();
          return;
        }
      }

      // Fallback: replace the hint with an icon line
      const helpline = document.createElement("div");
      helpline.className = "helpline";
      helpline.appendChild(btn);
      h.replaceWith(helpline);
    });

    // Ensure any existing help buttons are also aligned with the title row.
    root.querySelectorAll(".helpiconbtn[data-help]").forEach((btn) => {
      if (btn.closest(".rowhead")) return;
      const row = btn.closest(".row");
      if (!row) return;
      let rowhead = row.querySelector(":scope > .rowhead");
      if (!rowhead) {
        const firstLabel = row.querySelector(":scope > label");
        if (firstLabel) {
          rowhead = document.createElement("div");
          rowhead.className = "rowhead";
          row.insertBefore(rowhead, firstLabel);
          rowhead.appendChild(firstLabel);
        }
      }
      if (rowhead) rowhead.appendChild(btn);
    });
  }


}

    // Final guard in case something registered it between our initial check
    if (!customElements.get("snmp-switch-manager-card-editor")) {
      customElements.get("snmp-switch-manager-card-editor") || customElements.define("snmp-switch-manager-card-editor", SnmpSwitchManagerCardEditor);
    }
  });
}
