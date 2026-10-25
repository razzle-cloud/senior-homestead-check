// Address check: calls the public lookup function and explains the result in plain words.
// Works in English (index.html) and Spanish (es.html), based on <html lang>.
(function () {
  const FN = "https://kwmfcuwqplcfruolrjhz.supabase.co/functions/v1/lookup";
  const ES = (document.documentElement.lang || "").startsWith("es");
  const APPLY = ES ? "solicitar.html" : "apply.html";
  const form = document.getElementById("lookup-form");
  const input = document.getElementById("address");
  const btn = form.querySelector("button");
  const out = document.getElementById("results");

  const T = ES ? {
    btn: "Revisar mi dirección", busy: "Revisando…",
    cityOnFile: "Registradas con la Ciudad de Decatur", countyOnFile: "Registradas con el Condado de DeKalb",
    cityNone: "No hay exenciones en la factura 2026 de la Ciudad.", noBill: "No encontramos una factura 2026 de la Ciudad para esta propiedad.",
    countyNone: "No hay exenciones registradas para 2026.", countyUnchecked: "Todavía no hemos revisado los registros de DeKalb para esta propiedad.",
    since: "desde", worth: "Vale la pena revisar", howApply: "Cómo solicitar en cada oficina",
    allGood: "<strong>No vemos nada pendiente.</strong> Según los registros, las exenciones de las dos oficinas coinciden. Si un propietario cumplió 62, 65, 70 u 80 años recientemente, revise la lista de abajo: las exenciones por edad nunca se agregan automáticamente.",
    seniorSummary: "Exenciones de la Ciudad para propietarios de 62 años o más",
    th: ["Código", "Edad", "Límite de ingresos", "Monto", "Esta vivienda"], onFile: "Registrada", notOnFile: "No registrada",
    seniorNote: `Cada una requiere su propia solicitud a la Ciudad, con prueba de edad y, si hay límite de ingresos, la declaración de impuestos del año anterior. Las exenciones de DeKalb para personas mayores son aparte; vea <a href="solicitar.html">cómo solicitar</a>.`,
    foot: "Registros a septiembre de 2026, de las facturas de impuestos de la Ciudad de Decatur y de los registros de exenciones del Condado de DeKalb. Esta es información general, no asesoría tributaria ni legal. Cada oficina toma la decisión final sobre cada solicitud.",
    save: (amt, who) => `Ahorro estimado: unos ${amt} al año en impuestos ${who === "city" ? "de la Ciudad" : "del Condado"}.`,
    upTo: (amt) => `Si califica: hasta unos ${amt} al año.`,
    seniorCode: "una exención para mayores",
    empty: "Escriba su dirección, empezando por el número de la casa.",
    need: "Incluya el número y el nombre de la calle, por ejemplo <strong>123 Main St</strong>.",
    notFound: "Ninguna propiedad residencial en la Ciudad de Decatur coincide con esa dirección. Revise la ortografía o intente sin el tipo de calle (por ejemplo <strong>123 Main</strong>). Las viviendas fuera de los límites de la Ciudad no están incluidas.",
    addUnit: (n, q) => `Esa dirección tiene ${n} unidades. Agregue su número de unidad, por ejemplo <strong>${q} Unit 4</strong>.`,
    rate: "Ha revisado muchas direcciones en poco tiempo. Espere una hora e intente de nuevo.",
    busyMsg: "El servicio está ocupado en este momento. Intente más tarde hoy.",
    fail: "La revisión no funcionó esta vez. Intente de nuevo en un minuto.",
    offline: "No se pudo conectar. Revise su conexión a internet e intente de nuevo.",
    senior: [
      ["GH-2", "65 o más", "Sin límite de ingresos", "$15,000 menos del valor tributable de la Ciudad"],
      ["GH-3", "62 o más", "Ingreso tributable de Georgia menor de $60,000", "$25,000 menos del valor tributable de la Ciudad"],
      ["GS-1", "62 o más", "Ingreso del hogar menor de $25,000", "$50,000 menos del valor de la Ciudad y escolar"],
      ["S-1", "62 o más", "Ingreso menor de $10,000, sin contar jubilación", "$10,000 menos del valor escolar"],
      ["S-5", "65 a 69", "Ingreso bruto ajustado federal menor de $62,000", "$200,000 menos del valor escolar"],
      ["S-3 / S-6", "70 o más", "Sin límite de ingresos", "$50,000 a $200,000 menos del valor escolar"],
      ["S-2", "80 o más", "Ingreso bruto ajustado federal menor de $40,000", "Todos los impuestos escolares"],
    ],
  } : {
    btn: "Check my address", busy: "Checking…",
    cityOnFile: "On file with the City of Decatur", countyOnFile: "On file with DeKalb County",
    cityNone: "No exemptions on the 2026 city bill.", noBill: "No 2026 city tax bill was found for this property.",
    countyNone: "No exemptions on file for 2026.", countyUnchecked: "We haven't checked DeKalb's records for this property yet.",
    since: "since", worth: "Worth looking into", howApply: "How to apply to each office",
    allGood: "<strong>Nothing stands out.</strong> Based on the records, the exemptions on file at the two offices match each other. If an owner has turned 62, 65, 70 or 80 recently, check the list below: new age-based exemptions are never added automatically.",
    seniorSummary: "City exemptions for owners 62 and older",
    th: ["Code", "Age", "Income limit", "Amount", "This home"], onFile: "On file", notOnFile: "Not on file",
    seniorNote: `Each one needs its own application to the city, with proof of age and, where there's an income limit, last year's tax return. DeKalb's senior exemptions are separate; see <a href="apply.html">how to apply</a>.`,
    foot: "Records as of September 2026, from City of Decatur tax bills and DeKalb County exemption records. This is general information, not tax or legal advice. Each office makes the final decision on any application.",
    save: (amt, who) => `Estimated saving: about ${amt} a year in ${who} tax.`,
    upTo: (amt) => `If you qualify: up to about ${amt} a year.`,
    seniorCode: "a senior code",
    empty: "Type your street address, starting with the house number.",
    need: "Include the house number and street name, for example <strong>123 Main St</strong>.",
    notFound: "No residential property in the City of Decatur matches that address. Check the spelling, or try without the street type (for example <strong>123 Main</strong>). Homes outside city limits aren't included.",
    addUnit: (n, q) => `That address has ${n} units. Add your unit number, for example <strong>${q} Unit 4</strong>.`,
    rate: "You've checked a lot of addresses in a short time. Please wait an hour and try again.",
    busyMsg: "The address check is busy right now. Please try again later today.",
    fail: "The address check didn't work this time. Please try again in a minute.",
    offline: "The address check couldn't be reached. Check your internet connection and try again.",
    senior: [
      ["GH-2", "65 or older", "No income limit", "$15,000 off city taxable value"],
      ["GH-3", "62 or older", "Georgia taxable income under $60,000", "$25,000 off city taxable value"],
      ["GS-1", "62 or older", "Household income under $25,000", "$50,000 off city and school value"],
      ["S-1", "62 or older", "Income under $10,000, not counting retirement", "$10,000 off school value"],
      ["S-5", "65 to 69", "Federal adjusted gross income under $62,000", "$200,000 off school value"],
      ["S-3 / S-6", "70 or older", "No income limit", "$50,000 to $200,000 off school value"],
      ["S-2", "80 or older", "Federal adjusted gross income under $40,000", "All school tax"],
    ],
  };

  // Spanish names for exemption codes (the database stores English names)
  const ES_NAMES = {
    "GH-1": "Homestead general", "GH-2": "Homestead general A (65+)", "GH-3": "Homestead general 3 (62+, con límite de ingresos)",
    "GS-1": "General y escolar (62+, con límite de ingresos)", "S-1": "Escolar (62+, con límite de ingresos)",
    "S-2": "Escolar (80+, con límite de ingresos)", "S-3": "Escolar (70+)", "S-5": "Escolar (65–69, con límite de ingresos)",
    "S-6": "Escolar (70+)", "DV": "Veterano discapacitado", "LT-1": "Fideicomiso de tierras (Land Trust)",
    "H1": "Homestead básica", "H1S": "Básica + exención estatal para mayores", "H3": "Mayores (62+, con límite de ingresos)",
    "H4": "Mayores (65+, con límite de ingresos)", "H5": "Veterano discapacitado", "H5S": "Veterano discapacitado + mayores",
    "H6": "Mayores (62/65+, con límite de ingresos)", "H6I": "Mayores (62/65+, con límite de ingresos)",
    "H6D": "Discapacidad (menores de 62, con límite de ingresos)", "H7": "Mayores (62+, con límite de ingresos)",
    "H8": "Mayores (65+, con límite de ingresos)", "H9": "Mayores (70+, con límite de ingresos)",
    "H10": "Veterano discapacitado mayor (65+)",
  };
  function exName(c) {
    if (!ES) return c.name;
    const base = String(c.code).replace(/F$/, "");
    const n = ES_NAMES[c.code] || ES_NAMES[base];
    if (!n) return c.name;
    return n + (c.code !== base && !ES_NAMES[c.code] ? " (con valor congelado)" : "");
  }

  const money = (n) => (n == null || n === 0 ? null : "$" + Math.round(n).toLocaleString("en-US"));
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function advice(g, home) {
    const cs = esc(home.county.filter((c) => /^H(1S|3|4|6|7|8|9|10|5S)/.test(c.code)).map((c) => c.code).join(", ") || T.seniorCode);
    const save = (amt, who) => (money(amt) ? `<p class="save">${T.save(money(amt), who)}</p>` : "");
    const E = {
      CITY_BASIC_MISSING: ES
        ? { strong: true, h: "Solicite la exención homestead de la Ciudad de Decatur (GH-1)", p: "El Condado de DeKalb tiene registrada una exención homestead para esta vivienda, pero la Ciudad de Decatur no. La Ciudad necesita su propia solicitud; la que se presenta con DeKalb no la cubre.", s: save(g.city_savings, "city") }
        : { strong: true, h: "Apply for the City of Decatur homestead exemption (GH-1)", p: "DeKalb County has a homestead exemption on file for this home, but the City of Decatur does not. The city needs its own application; filing with DeKalb does not cover it.", s: save(g.city_savings, "city") },
      COUNTY_BASIC_MISSING: ES
        ? { strong: true, h: "Solicite la exención homestead del Condado de DeKalb", p: "La Ciudad de Decatur tiene registrada una exención homestead para esta vivienda, pero el Condado de DeKalb no. Si esta es su vivienda principal, puede solicitarla con DeKalb en línea o en persona.", s: save(g.county_savings, "county") }
        : { strong: true, h: "Apply for the DeKalb County homestead exemption", p: "The City of Decatur has a homestead exemption on file for this home, but DeKalb County does not. If this is your main home, you can file with DeKalb online or in person.", s: save(g.county_savings, "county") },
      GH2_MISSING: ES
        ? { strong: true, h: "Pregunte a la Ciudad por la GH-2, la exención para propietarios de 65 años o más", p: `DeKalb tiene registrada una exención para mayores (${cs}), lo que normalmente indica que un propietario tiene 65 años o más. La GH-2 de la Ciudad no tiene límite de ingresos y no está registrada con la Ciudad.`, s: save(g.city_savings, "city") }
        : { strong: true, h: "Ask the city about GH-2, the exemption for owners 65 and older", p: `DeKalb has a senior exemption on file (${cs}), which usually means an owner is 65 or older. The city's GH-2 has no income limit, and it is not on file with the city.`, s: save(g.city_savings, "city") },
      GH3_MISSING: ES
        ? { strong: true, h: "Pregunte a la Ciudad por la GH-3, para propietarios de 62 años o más con ingresos más bajos", p: `DeKalb tiene registrada una exención para mayores (${cs}) con un límite de ingresos más bajo que el de la GH-3 de la Ciudad, que permite un ingreso tributable de Georgia de hasta $60,000. Si calificó con DeKalb, es muy probable que califique para la GH-3.`, s: save(g.city_savings, "city") }
        : { strong: true, h: "Ask the city about GH-3, for owners 62 and older with lower incomes", p: `DeKalb has a senior exemption on file (${cs}) with a lower income limit than the city's GH-3, which allows Georgia taxable income up to $60,000. If you qualified with DeKalb, you very likely qualify for GH-3.`, s: save(g.city_savings, "city") },
      SCHOOL_70_MISSING: ES
        ? { strong: true, h: "Pregunte a la Ciudad por la exención escolar para propietarios de 70 años o más", p: "Los registros muestran un propietario de 70 años o más. Las exenciones S-3 y S-6 de la Ciudad para mayores de 70 no tienen límite de ingresos, y ninguna está registrada.", s: save(g.city_savings, "city") }
        : { strong: true, h: "Ask the city about the school tax exemption for owners 70 and older", p: "Records on file show an owner who is 70 or older. The city's S-3 and S-6 exemptions for 70+ have no income limit, and neither is on file.", s: save(g.city_savings, "city") },
      SCHOOL_65_MISSING: ES
        ? { strong: false, h: "Revise las exenciones escolares de la Ciudad para personas mayores", p: "Los registros muestran un propietario de 65 años o más, pero ninguna exención escolar de la Ciudad. Si un propietario tiene entre 65 y 69 años y un ingreso bruto ajustado federal menor de $62,000, la S-5 resta hasta $200,000 del valor sujeto a impuestos escolares. A los 70, la S-6 no tiene límite de ingresos.", s: money(g.city_savings) ? `<p class="save">${T.upTo(money(g.city_savings))}</p>` : "" }
        : { strong: false, h: "Check the city's school tax exemptions for seniors", p: "Records on file show an owner who is 65 or older, but no city school tax exemption. If an owner is 65 to 69 with federal adjusted gross income under $62,000, S-5 removes up to $200,000 of value from school tax. At 70, S-6 needs no income test.", s: money(g.city_savings) ? `<p class="save">${T.upTo(money(g.city_savings))}</p>` : "" },
      COUNTY_SENIOR_MISSING: ES
        ? { strong: false, h: "Revise las exenciones del Condado de DeKalb para personas mayores", p: "La Ciudad tiene registrada una exención para mayores en esta vivienda, pero DeKalb solo tiene la exención básica o ninguna. Las exenciones de DeKalb para mayores tienen límites de ingresos; revise si alguna le corresponde.", s: "" }
        : { strong: false, h: "Check DeKalb County's senior exemptions", p: "The city has a senior exemption on file for this home, but DeKalb has only its basic exemption or none. DeKalb's senior exemptions have income limits, so check whether one fits.", s: "" },
    };
    return E[g.code] || null;
  }

  function list(items, emptyText) {
    if (!items.length) return `<p class="none">${emptyText}</p>`;
    return "<ul>" + items.map((c) => `<li><span class="code">${esc(c.code)}</span> ${esc(exName(c))}${c.year_applied ? ` <span class="muted small">${T.since} ${c.year_applied}</span>` : ""}</li>`).join("") + "</ul>";
  }

  function render(home) {
    const items = home.gaps.map((g) => advice(g, home)).filter(Boolean);
    const cityCodes = new Set(home.city.map((c) => c.code));
    const seniorRows = T.senior.map(([code, age, income, amount]) => {
      const onFile = code.split(" / ").some((c) => cityCodes.has(c));
      return `<tr><td><strong>${code}</strong></td><td>${age}</td><td>${income}</td><td>${amount}</td><td>${onFile ? T.onFile : T.notOnFile}</td></tr>`;
    }).join("");
    if (!items.length && !home.city.length && !home.county.length) {
      items.push(ES
        ? { strong: true, h: "No hay exención homestead en ninguna de las dos oficinas", p: "Si esta es su vivienda principal, puede solicitar la exención homestead con el Condado de DeKalb y con la Ciudad de Decatur. Son solicitudes separadas. Si la vivienda es de alquiler o una segunda vivienda, no califica.", s: "" }
        : { strong: true, h: "No homestead exemption at either office", p: "If this is your main home, you can apply for a homestead exemption with both DeKalb County and the City of Decatur. They are separate applications. If the home is a rental or second home, it doesn't qualify.", s: "" });
    }
    const todo = items.length
      ? `<div class="todo"><h3>${T.worth}</h3>${items.map((a) => `<div class="todo-item${a.strong ? "" : " soft"}"><h4>${a.h}</h4><p>${a.p}</p>${a.s}</div>`).join("")}<p class="small"><a href="${APPLY}">${T.howApply}</a></p></div>`
      : `<div class="allgood">${T.allGood}</div>`;
    return `<article class="home">
      <h2>${esc(home.address)}</h2>
      <div class="onfile">
        <section><h3>${T.cityOnFile}</h3>${home.has_city_bill ? list(home.city, T.cityNone) : `<p class="none">${T.noBill}</p>`}</section>
        <section><h3>${T.countyOnFile}</h3>${home.county_checked ? list(home.county, T.countyNone) : `<p class="none">${T.countyUnchecked}</p>`}</section>
      </div>
      ${todo}
      <details><summary>${T.seniorSummary}</summary>
        <div class="table-wrap"><table><thead><tr>${T.th.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${seniorRows}</tbody></table></div>
        <p class="small">${T.seniorNote}</p>
      </details>
    </article>`;
  }

  function message(html, error) {
    out.innerHTML = `<div class="status-msg${error ? " error" : ""}" role="status">${html}</div>`;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (!q) { message(T.empty, true); input.focus(); return; }
    btn.disabled = true; btn.textContent = T.busy;
    try {
      const r = await fetch(FN, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ q }) });
      const d = await r.json();
      switch (d.status) {
        case "ok": out.innerHTML = d.results.map(render).join("") + `<p class="small muted">${T.foot}</p>`; break;
        case "need_number_and_street": message(T.need, true); break;
        case "not_found": message(T.notFound, true); break;
        case "add_unit": message(T.addUnit(d.count, esc(q)), true); break;
        case "rate_limited": message(T.rate, true); break;
        case "busy": message(T.busyMsg, true); break;
        default: message(T.fail, true);
      }
    } catch (err) {
      message(T.offline, true);
    } finally {
      btn.disabled = false; btn.textContent = T.btn;
      out.querySelector("h2, .status-msg")?.setAttribute("tabindex", "-1");
      out.querySelector("h2, .status-msg")?.focus();
    }
  });
})();
