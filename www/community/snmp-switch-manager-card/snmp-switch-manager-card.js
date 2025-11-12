class SnmpSwitchManagerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;

    // Registries / scoping
    this._entityReg = null;
    this._deviceReg = null;
    this._anchorDeviceId = null;

    // Persist modal AND its stylesheet across renders
    this._modalEl = null;
    this._modalStyle = null;
  }

  setConfig(config) {
    this._config = {
      title: config.title ?? "",
      view: (config.view === "panel" ? "panel" : "list"),
      ports_per_row: Number.isFinite(config.ports_per_row) ? Number(config.ports_per_row) : 24,
      panel_width: Number.isFinite(config.panel_width) ? Number(config.panel_width) : 740,
      port_size: Number.isFinite(config.port_size) ? Number(config.port_size) : 18,
      gap: Number.isFinite(config.gap) ? Number(config.gap) : 10,
      show_labels: config.show_labels !== false,
      label_size: Number.isFinite(config.label_size) ? Number(config.label_size) : 8,

      // NEW: choose where Diagnostics/Virtual block appears
      info_position: (config.info_position === "below") ? "below" : "above",

      // Scoping
      anchor_entity: config.anchor_entity ?? null,
      device_name: config.device_name ?? null,
      unit: Number.isFinite(config.unit) ? Number(config.unit) : null,
      slot: Number.isFinite(config.slot) ? Number(config.slot) : null,
      ports: Array.isArray(config.ports) ? config.ports : null,

      // Diagnostics sensor list
      diagnostics: Array.isArray(config.diagnostics) ? config.diagnostics : [],
    };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() { return 5; }

  // ---------- registries ----------
  async _ensureRegistries() {
    if (!this._hass) return;
    const tasks = [];
    if (!this._entityReg)
      tasks.push(this._hass.callWS({ type: "config/entity_registry/list" }).then(r => this._entityReg = r));
    if (!this._deviceReg)
      tasks.push(this._hass.callWS({ type: "config/device_registry/list" }).then(r => this._deviceReg = r));
    if (tasks.length) await Promise.all(tasks).catch(()=>{});
  }
  _deviceIdForEntity(entity_id) {
    const row = this._entityReg?.find(e => e.entity_id === entity_id);
    return row?.device_id ?? null;
  }
  async _resolveAnchorDeviceId() {
    if (!this._config.anchor_entity) return null;
    await this._ensureRegistries();
    this._anchorDeviceId = this._deviceIdForEntity(this._config.anchor_entity);
    return this._anchorDeviceId;
  }

  // ---------- helpers ----------
  _parseTriple(name) {
    const m = String(name).toUpperCase().match(/^([A-Z]{2})(\d+)\/(\d+)\/(\d+)$/);
    if (!m) return null;
    return { kind: m[1], unit: +m[2], slot: +m[3], port: +m[4] };
  }
  _kindPriority(k) { k = String(k||"").toUpperCase(); return k==="GI"?0 : k==="TE"?1 : k==="TW"?2 : 3; }

  _entityMatchesNameUnitSlot(id, st) {
    const attrs = st?.attributes || {};
    const name = String(attrs.Name || id.split(".")[1] || "");
    if (this._config.device_name) {
      const needle = String(this._config.device_name).toLowerCase();
      const fn = String(attrs.friendly_name || "").toLowerCase();
      if (!fn.includes(needle) && !id.toLowerCase().includes(needle)) return false;
    }
    if (this._config.unit!=null || this._config.slot!=null) {
      const t = this._parseTriple(name); if (!t) return false;
      if (this._config.unit!=null && t.unit!==this._config.unit) return false;
      if (this._config.slot!=null && t.slot!==this._config.slot) return false;
    }
    return true;
  }

  async _discoverEntities() {
    const H = this._hass?.states || {};
    const explicit = Array.isArray(this._config.ports) && this._config.ports.length;

    if (this._config.anchor_entity && !this._anchorDeviceId) {
      await this._resolveAnchorDeviceId();
      this._render(); // allow re-render
    }

    const entries = explicit
      ? this._config.ports.map(id => [id, H[id]]).filter(([,st]) => !!st)
      : Object.entries(H).filter(([id, st]) => {
          if (!id.startsWith("switch.")) return false;
          if (!st?.attributes) return false;

          const attrs = st.attributes;
          const looksRight =
            (attrs.Index!==undefined || attrs.Name) ||
            /^switch\.(?:gi|te|tw)\d+_\d+_\d+$/i.test(id) ||
            /^switch\.(?:vl\d+|lo\d+|po\d+)$/i.test(id);
          if (!looksRight) return false;

          if (this._anchorDeviceId && this._entityReg) {
            const did = this._deviceIdForEntity(id);
            if (!did || did !== this._anchorDeviceId) return false;
          } else {
            if (!this._entityMatchesNameUnitSlot(id, st)) return false;
          }
          return true;
        });

    if (!entries.length && !explicit) {
      const candidates = Object.keys(H).filter(k => k.startsWith("switch.")).slice(0,20);
      return { phys:[], virt:[], diag:candidates };
    }

    const phys=[], virt=[];
    for (const [id, st] of entries) {
      const n = String(st.attributes?.Name || id.split(".")[1] || "").toUpperCase();
      if (/^(GI|TE|TW)/.test(n) || /^switch\.(gi|te|tw)\d+_\d+_\d+$/i.test(id)) phys.push([id,st]);
      else virt.push([id,st]);
    }

    phys.sort((a,b)=>{
      const na=a[1].attributes?.Name||a[0], nb=b[1].attributes?.Name||b[0];
      const ta=this._parseTriple(na), tb=this._parseTriple(nb);
      const ka=this._kindPriority(ta?.kind), kb=this._kindPriority(tb?.kind);
      if (ka!==kb) return ka-kb;
      if ((ta?.unit??1e9)!==(tb?.unit??1e9)) return (ta?.unit??1e9)-(tb?.unit??1e9);
      if ((ta?.slot??1e9)!==(tb?.slot??1e9)) return (ta?.slot??1e9)-(tb?.slot??1e9);
      if ((ta?.port??1e9)!==(tb?.port??1e9)) return (ta?.port??1e9)-(tb?.port??1e9);
      return String(na).localeCompare(String(nb), undefined, {numeric:true,sensitivity:"base"});
    });

    virt.sort((a,b)=>{
      const na=String(a[1].attributes?.Name||a[0]);
      const nb=String(b[1].attributes?.Name||b[0]);
      return na.localeCompare(nb, undefined, {numeric:true,sensitivity:"base"});
    });

    return { phys, virt, diag:null };
  }

  _colorFor(st) {
    const a=String(st.attributes?.Admin||"").toLowerCase();
    const o=String(st.attributes?.Oper||"").toLowerCase();
    if (a==="down") return "#f59e0b";
    if (a==="up" && o==="up") return "#22c55e";
    if (a==="up" && o==="down") return "#ef4444";
    return "#9ca3af";
  }
  _buttonLabel(st){ return (st.state||"").toLowerCase()==="on" ? "Turn off" : "Turn on"; }
  _toggle(entity_id){
    const st=this._hass?.states?.[entity_id]; if(!st) return;
    const on=(st.state||"").toLowerCase()==="on";
    this._hass.callService("switch", on?"turn_off":"turn_on", { entity_id });
  }

  _openDialog(entity_id){
    const st=this._hass?.states?.[entity_id]; if(!st) return;
    const attrs=st.attributes||{};
    const name=attrs.Name || entity_id.split(".")[1];
    const ip=attrs.IP ? `<div><b>IP:</b> ${attrs.IP}</div>` : "";

    // remove any prior modal/style
    this._modalEl?.remove(); this._modalStyle?.remove();

    this._modalEl = document.createElement("div");
    this._modalEl.className = "ssm-modal-root";
    this._modalEl.innerHTML = `
      <div class="ssm-backdrop"></div>
      <div class="ssm-modal" role="dialog" aria-modal="true">
        <div class="ssm-modal-title">${name}</div>
        <div class="ssm-modal-body">
          <div><b>Admin:</b> ${attrs.Admin ?? "-"}</div>
          <div><b>Oper:</b> ${attrs.Oper ?? "-"}</div>
          ${ip}
          <div><b>Index:</b> ${attrs.Index ?? "-"}</div>
          <div><b>Alias:</b> ${attrs.Alias ?? "-"}</div>
        </div>
        <div class="ssm-modal-actions">
          <button class="btn wide" data-entity="${entity_id}">${this._buttonLabel(st)}</button>
          <button class="btn subtle" data-close="1">Close</button>
        </div>
      </div>
    `;

    // Persist this stylesheet across renders too
    this._modalStyle = document.createElement("style");
    this._modalStyle.textContent = `
      .ssm-backdrop{position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:10000;}
      .ssm-modal{position:fixed;z-index:10001;left:50%;top:50%;transform:translate(-50%,-50%);
        min-width:320px;max-width:90vw;background:var(--card-background-color);
        color:var(--primary-text-color);border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.5);padding:16px;}
      .ssm-modal-title{font-weight:700;font-size:18px;margin-bottom:8px}
      .ssm-modal-body div{margin:4px 0}
      .ssm-modal-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:12px}
      .btn{font:inherit;padding:8px 12px;border-radius:10px;border:1px solid var(--divider-color);
        background:var(--secondary-background-color);cursor:pointer}
      .btn.wide{flex:1;text-align:center}
      .btn.subtle{background:transparent}
    `;

    const close = () => {
      this._modalEl?.remove(); this._modalStyle?.remove();
      this._modalEl = null; this._modalStyle = null;
    };

    this._modalEl.querySelector(".ssm-backdrop")?.addEventListener("click", close);
    this._modalEl.querySelector("[data-close]")?.addEventListener("click", close);
    this._modalEl.querySelector(".ssm-modal")?.addEventListener("click", (e)=>e.stopPropagation());
    this._modalEl.querySelector(".btn.wide")?.addEventListener("click",(ev)=>{
      const id=ev.currentTarget.getAttribute("data-entity");
      this._toggle(id);
      setTimeout(()=>this._render(), 300);
    });

    // Append both style and modal
    this.shadowRoot.append(this._modalStyle, this._modalEl);
  }

  async _render(){
    if (!this.shadowRoot || !this._config || !this._hass) return;

    const data = await this._discoverEntities(); if (!data) return;
    const { phys, virt, diag } = data;

    const style = `
      :host { display:block; }
      ha-card { display:block; }
      .head { font-size: 18px; font-weight: 600; padding: 12px 16px; border-bottom: 1px solid var(--divider-color); }
      .section { padding: 12px 16px; }
      .hint { opacity:.85; }
      .grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(170px,1fr)); gap:10px; }
      .port { border:1px solid var(--divider-color); border-radius:12px; padding:10px; background:var(--card-background-color); }
      .name { font-weight:700; margin-bottom:6px; }
      .kv { font-size:12px; color:var(--secondary-text-color); margin-bottom:10px; }
      .dot { width:10px; height:10px; border-radius:50%; display:inline-block; margin-right:6px; }
      .btn { font:inherit; padding:10px 12px; border-radius:10px; border:1px solid var(--divider-color); background:var(--secondary-background-color); cursor:pointer; }
      .btn:active { transform: translateY(1px); }
      .btn.wide { width:100%; text-align:center; }

      /* Info grid */
      .info-grid { display:grid; grid-template-columns: 1fr 1fr; gap:12px; padding: 0 16px 8px; }
      @media (max-width: 860px) { .info-grid { grid-template-columns: 1fr; } }
      .box { border:1px solid var(--divider-color); border-radius:12px; padding:10px; background:var(--card-background-color); }

      .virt-title { font-weight:700; margin-bottom:6px; }
      .virt-row { display:flex; align-items:center; gap:8px; padding:6px 0; font-size:14px; }
      .virt-row .btn { padding:6px 10px; font-size:12px; margin-left:auto; }

      .diag-title { font-weight:700; margin-bottom:6px; }
      .diag-row { display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px dashed var(--divider-color); }
      .diag-name { opacity:.9; }
      .diag-val { opacity:.8; }

      /* Panel */
      .panel { padding: 8px 12px 6px; }
      svg { display:block; }
      .label { font-size: ${this._config.label_size}px; fill: var(--primary-text-color); opacity:.85; }
      .panel-wrap { border-radius:12px; border:1px solid var(--divider-color);
        padding:6px; background: color-mix(in oklab, var(--ha-card-background, #1f2937) 75%, transparent); }
    `;

    const header = this._config.title ? `<div class="head">${this._config.title}</div>` : "";

    if (diag && !phys.length && !virt.length && !this._config.ports) {
      const diagList = diag.map(id=>`<code>${id}</code>`).join(", ");
      this.shadowRoot.innerHTML = `
        <ha-card>
          <style>${style}</style>
          ${header}
          <div class="section"><div class="hint">
            Auto-discovery found no matching ports.<br/>
            First 20 <b>switch.*</b> entities: ${diagList || "<i>(none)</i>"}
          </div></div>
        </ha-card>`;
      // Re-attach modal/style if open
      if (this._modalStyle) this.shadowRoot.append(this._modalStyle);
      if (this._modalEl) this.shadowRoot.append(this._modalEl);
      return;
    }

    // Info grid (Diagnostics + Virtual)
    const infoGrid = (() => {
      const diagBox = (() => {
        if (!this._config.diagnostics?.length) return "";
        const H=this._hass?.states||{};
        const rows=this._config.diagnostics.map(id=>{
          const st=H[id]; if(!st) return null;
          const name=st.attributes?.friendly_name||id;
          const value=typeof st.state==="string"?st.state:JSON.stringify(st.state);
          return `<div class="diag-row"><span class="diag-name">${name}</span><span class="diag-val">${value}</span></div>`;
        }).filter(Boolean).join("");
        if (!rows) return "";
        return `<div class="box"><div class="diag-title">Diagnostics</div>${rows}</div>`;
      })();

      const virtBox = (() => {
        if (!virt.length) return "";
        const rows = virt.map(([id, st])=>{
          const n=st.attributes?.Name || id.split(".")[1] || id;
          const ip=st.attributes?.IP ? ` — ${st.attributes.IP}` : "";
          return `<div class="virt-row">
            <span class="dot" style="background:${this._colorFor(st)}"></span>
            <span>${n}${ip}</span>
            <button class="btn" data-entity="${id}">${this._buttonLabel(st)}</button>
          </div>`;
        }).join("");
        return `<div class="box"><div class="virt-title">Virtual Interfaces</div>${rows}</div>`;
      })();

      if (!diagBox && !virtBox) return "";
      return `<div class="info-grid">${diagBox}${virtBox}</div>`;
    })();

    const listView = () => {
      const grid = phys.map(([id, st])=>{
        const a=st.attributes||{};
        const name=a.Name || id.split(".")[1];
        const ip = a.IP ? ` • IP: ${a.IP}` : "";
        return `<div class="port">
          <div class="name">${name}</div>
          <div class="kv"><span class="dot" style="background:${this._colorFor(st)}"></span>
            Admin: ${a.Admin ?? "-"} • Oper: ${a.Oper ?? "-"}${ip}
          </div>
          <button class="btn wide" data-entity="${id}">${this._buttonLabel(st)}</button>
        </div>`;
      }).join("");

      return `
        ${this._config.info_position==="above" ? infoGrid : ""}
        <div class="section">
          ${phys.length ? `<div class="grid">${grid}</div>` : `<div class="hint">No physical ports discovered.</div>`}
        </div>
        ${this._config.info_position==="below" ? infoGrid : ""}`;
    };

    const panelView = () => {
      const P=this._config.port_size, G=this._config.gap, perRow=Math.max(1,this._config.ports_per_row);
      const rows=Math.max(1, Math.ceil((phys.length||perRow)/perRow));
      const W=this._config.panel_width;
      const topPad=24, sidePad=28, rowPad=(this._config.show_labels? (this._config.label_size+14):18);
      const H=20+topPad+rows*(P+G)+rowPad;
      const plate = `<rect x="10" y="10" width="${W-20}" height="${H-20}" rx="8"
        fill="var(--ha-card-background, #1f2937)" stroke="var(--divider-color, #4b5563)"/>`;
      const usableW=W-2*sidePad, slotW=usableW/perRow;

      const rects = phys.map(([id, st], i)=>{
        const name = String(st.attributes?.Name || id.split(".")[1] || "");
        const idx=i%perRow, row=Math.floor(i/perRow);
        const x=sidePad+idx*slotW+(slotW-P)/2, y=topPad+row*(P+G)+18;
        const fill=this._colorFor(st);
        const label = this._config.show_labels
          ? `<text class="label" x="${x+P/2}" y="${y+P+this._config.label_size}" text-anchor="middle">${name}</text>`
          : "";
        return `
          <g class="port-svg" data-entity="${id}" tabindex="0" style="cursor:pointer">
            <rect x="${x}" y="${y}" width="${P}" height="${P}" rx="${Math.round(P*0.2)}"
              fill="${fill}" stroke="rgba(0,0,0,.35)"/>
            ${label}
          </g>`;
      }).join("");

      const svg = `
        <div class="panel-wrap">
          <svg viewBox="0 0 ${W} ${H}" width="100%" height="auto" preserveAspectRatio="xMidYMid meet">
            ${plate}
            ${rects}
          </svg>
        </div>`;

      return `
        ${this._config.info_position==="above" ? infoGrid : ""}
        <div class="panel">${svg}</div>
        ${this._config.info_position==="below" ? infoGrid : ""}`;
    };

    const body = this._config.view === "panel" ? panelView() : listView();

    this.shadowRoot.innerHTML = `
      <ha-card>
        <style>${style}</style>
        ${header}
        ${body}
      </ha-card>
    `;

    // wire list buttons
    this.shadowRoot.querySelectorAll(".btn[data-entity]").forEach(btn=>{
      btn.addEventListener("click",(ev)=>{
        const id=ev.currentTarget.getAttribute("data-entity");
        if (id) this._toggle(id);
      });
    });

    // wire panel ports -> modal
    this.shadowRoot.querySelectorAll(".port-svg[data-entity]").forEach(g=>{
      g.addEventListener("click",(ev)=>{
        const id=ev.currentTarget.getAttribute("data-entity");
        if (id) this._openDialog(id);
      });
      g.addEventListener("keypress",(ev)=>{
        if (ev.key==="Enter" || ev.key===" ") {
          ev.preventDefault();
          const id=ev.currentTarget.getAttribute("data-entity");
          if (id) this._openDialog(id);
        }
      });
    });

    // Re-attach modal AND style if they exist (so it stays styled and centered)
    if (this._modalStyle) this.shadowRoot.append(this._modalStyle);
    if (this._modalEl) this.shadowRoot.append(this._modalEl);
  }
}

customElements.define("snmp-switch-manager-card", SnmpSwitchManagerCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "snmp-switch-manager-card",
  name: "SNMP Switch Manager Card",
  description: "Auto-discovers SNMP Switch Manager ports with panel/list views, safe modal toggles, and diagnostics.",
  preview: true
});
