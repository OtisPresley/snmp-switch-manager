class SnmpSwitchManagerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._needsAuto = false;
    this._autoStarted = false;
  }

  setConfig(config) {
    const rawPorts = config.ports ?? config.entities;

    if (Array.isArray(rawPorts) && rawPorts.length > 0) {
      const normalize = (entry) => {
        if (typeof entry === "string") return { entity: entry };
        if (!entry || !entry.entity)
          throw new Error("Each port entry must include an entity property.");
        return { ...entry };
      };

      const ports = rawPorts.map(normalize);

      const markerSize = Number(config.marker_size ?? 26);
      this._config = {
        title: config.title,
        image: config.image,
        layout:
          config.layout ||
          (ports.every((p) => Number.isFinite(p.x) && Number.isFinite(p.y))
            ? "image"
            : "grid"),
        marker_size:
          Number.isFinite(markerSize) && markerSize > 0 ? markerSize : 26,
        ports,
        device_id: config.device_id,
        device_name: config.device_name,
      };

      this._needsAuto = false;
      this._autoStarted = false;
      this._render();
      return;
    }

    this._config = {
      title: config.title,
      image: config.image,
      layout: config.layout || "grid",
      marker_size: Number(config.marker_size ?? 26),
      ports: [],
      device_id: config.device_id || null,
      device_name: config.device_name || null,
    };

    this._needsAuto = true;
    this._autoStarted = false;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;

    if (
      this._hass &&
      this._config &&
      this._needsAuto &&
      !this._autoStarted &&
      (!this._config.ports || this._config.ports.length === 0)
    ) {
      this._autoStarted = true;
      this._autoDiscoverPorts()
        .then((list) => {
          if (Array.isArray(list) && list.length) {
            this._config.ports = list.map((id) => ({ entity: id }));
            this._needsAuto = false;
            this._render();
          }
        })
        .catch(() => {});
    }

    this._render();
  }

  getCardSize() {
    return 4;
  }

  // ---------- Auto-discovery helpers ----------

  async _findDeviceIdByName(name) {
    const devices = await this._hass.callWS({
      type: "config/device_registry/list",
    });
    const dev = devices.find(
      (d) => d.name === name || d.name_by_user === name
    );
    return dev ? dev.id : null;
  }

  async _autoDiscoverPorts() {
    let deviceId = this._config.device_id || null;
    if (!deviceId && this._config.device_name) {
      deviceId = await this._findDeviceIdByName(this._config.device_name);
    }
    if (!deviceId) return [];

    const entities = await this._hass.callWS({
      type: "config/entity_registry/list",
    });

    const ours = entities
      .filter(
        (e) =>
          e.device_id === deviceId &&
          e.platform === "snmp_switch_manager" && // <- renamed platform
          e.domain === "switch"
      )
      .map((e) => e.entity_id);

    const withStates = ours
      .map((id) => ({ id, st: this._hass.states[id] }))
      .filter((x) => x.st);

    const filtered = withStates.filter(({ st }) => {
      const n = (st.attributes?.Name || "").toString().toUpperCase();
      return n !== "CPU";
    });

    filtered.sort((a, b) => {
      const ai = Number(a.st.attributes?.Index);
      const bi = Number(b.st.attributes?.Index);
      if (Number.isFinite(ai) && Number.isFinite(bi)) return ai - bi;
      return a.id.localeCompare(b.id);
    });

    return filtered.map((x) => x.id);
  }

  // ---------- Rendering ----------

  _render() {
    if (!this.shadowRoot) return;
    if (!this._config || !this._hass) {
      this.shadowRoot.innerHTML = `<ha-card><div class="card"><div>Loading…</div></div></ha-card>`;
      return;
    }

    const ports = (this._config.ports || [])
      .map((p) => {
        const id = p.entity;
        const st = this._hass.states[id];
        if (!st) return null;
        return {
          id,
          st,
          x: Number(p.x),
          y: Number(p.y),
        };
      })
      .filter(Boolean);

    const title = this._config.title || "";
    const layout = this._config.layout || "grid";
    const markerSize = Number(this._config.marker_size ?? 26);
    const image = this._config.image || null;

    const style = `
      :host { display:block; }
      ha-card { display:block; padding:0; }
      .card { padding: 16px; box-sizing: border-box; position: relative; }
      header { font-size: 20px; margin: 0 0 12px; }
      .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px; }
      .port {
        border-radius: 12px; padding: 10px; background: var(--card-background-color);
        border: 1px solid var(--divider-color);
      }
      .port .name { font-weight: 600; margin-bottom: 8px; }
      .kv { display:flex; justify-content: space-between; font-size: 12px; opacity: .8; }
      .imgwrap { position: relative; }
      .imgwrap img { display: block; width: 100%; border-radius: 12px; }
      .marker {
        position:absolute; width:${markerSize}px; height:${markerSize}px;
        border-radius:50%; border: 2px solid rgba(0,0,0,.2);
        display:flex; align-items:center; justify-content:center;
        transform: translate(-50%, -50%);
        background: var(--primary-color);
        color: #fff; font-size: 12px; cursor: pointer;
        box-shadow: 0 2px 6px rgba(0,0,0,.25);
      }
      .marker.off { background: var(--disabled-text-color); }
      .empty { opacity:.7; font-style: italic; }
      button.toggle {
        margin-top: 8px; width: 100%;
        border: none; border-radius: 8px; padding: 8px 10px;
        background: var(--primary-color); color: #fff; cursor: pointer;
      }
      button.toggle.off { background: var(--disabled-text-color); color: #222; }
    `;

    const headerHtml = title ? `<header>${title}</header>` : "";

    if (layout === "image" && image && ports.every((p) => Number.isFinite(p.x) && Number.isFinite(p.y))) {
      const markers = ports
        .map((p, idx) => {
          const on = (p.st.state || "").toLowerCase() === "on";
          const cls = on ? "marker" : "marker off";
          const top = `${p.y}%`;
          const left = `${p.x}%`;
          const label = this._prettyName(p.st, p.id);
          return `<div class="${cls}" title="${label}" style="top:${top};left:${left};" data-entity="${p.id}">${idx + 1}</div>`;
        })
        .join("");

      this.shadowRoot.innerHTML = `
        <ha-card>
          <style>${style}</style>
          <div class="card">
            ${headerHtml}
            <div class="imgwrap">
              <img src="${image}">
              ${markers}
            </div>
          </div>
        </ha-card>
      `;

      this.shadowRoot.querySelectorAll(".marker").forEach((el) => {
        el.addEventListener("click", (ev) => {
          const ent = ev.currentTarget.getAttribute("data-entity");
          if (ent) this._toggle(ent);
        });
      });

      return;
    }

    if (ports.length === 0) {
      this.shadowRoot.innerHTML = `
        <ha-card>
          <style>${style}</style>
          <div class="card">
            ${headerHtml}
            <div class="empty">No ports to display yet…</div>
          </div>
        </ha-card>
      `;
      return;
    }

    const portCards = ports
      .map((p) => {
        const st = p.st;
        const on = (st.state || "").toLowerCase() === "on";
        const cls = on ? "toggle" : "toggle off";
        const name = this._prettyName(st, p.id);
        const idx = st.attributes?.Index ?? "";
        const admin = st.attributes?.Admin ?? "";
        const oper = st.attributes?.Oper ?? "";
        const alias = st.attributes?.Alias ?? "";
        const ip = st.attributes?.IP ?? "";
        return `
          <div class="port">
            <div class="name">${name}</div>
            <div class="kv"><span>Index</span><span>${idx}</span></div>
            <div class="kv"><span>Alias</span><span>${alias}</span></div>
            <div class="kv"><span>Admin</span><span>${admin}</span></div>
            <div class="kv"><span>Oper</span><span>${oper}</span></div>
            ${ip ? `<div class="kv"><span>IP</span><span>${ip}</span></div>` : ``}
            <button class="${cls}" data-entity="${p.id}">${on ? "Turn Off" : "Turn On"}</button>
          </div>
        `;
      })
      .join("");

    this.shadowRoot.innerHTML = `
      <ha-card>
        <style>${style}</style>
        <div class="card">
          ${headerHtml}
          <div class="grid">
            ${portCards}
          </div>
        </div>
      </ha-card>
    `;

    this.shadowRoot.querySelectorAll("button.toggle").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        const ent = ev.currentTarget.getAttribute("data-entity");
        if (ent) this._toggle(ent);
      });
    });
  }

  _prettyName(stateObj, entityId) {
    const n = (stateObj.attributes?.Name || "").toString();
    return n || entityId;
  }

  _toggle(entity_id) {
    if (!this._hass) return;
    const st = this._hass.states[entity_id];
    const isOn = (st?.state || "").toLowerCase() === "on";
    const svc = isOn ? "turn_off" : "turn_on";
    this._hass.callService("switch", svc, { entity_id });
  }
}

// Register with the new tag name
customElements.define("snmp-switch-manager-card", SnmpSwitchManagerCard);

// Show in card picker
window.customCards = window.customCards || [];
window.customCards.push({
  type: "snmp-switch-manager-card",
  name: "SNMP Switch Manager",
  description: "Front view + port controls for the SNMP switch integration",
  preview: true,
});
