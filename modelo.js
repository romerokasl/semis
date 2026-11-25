// Ejecuta el XGBoost de Sunny.EMC en el navegador (sin servidor).
// El modelo (modelo_web.json) lo genera ml/entrenar.py. Entrenado con fallas SIMULADAS.
// Las variables deben coincidir con caracteristicas() de ml/etl.py.
(function (root) {
  const media = (a) => a.reduce((s, x) => s + x, 0) / a.length;
  const desviacion = (a) => { const m = media(a); return Math.sqrt(media(a.map(x => (x - m) ** 2))); };
  const pendiente = (a) => {
    const mx = (a.length - 1) / 2, my = media(a);
    let num = 0, den = 0;
    a.forEach((y, x) => { num += (x - mx) * (y - my); den += (x - mx) ** 2; });
    return num / den;
  };

  // w: arreglo de registros crudos de Firebase {volt, luz, tds, tdht, hum}
  function caracteristicas(w) {
    const v = w.map(r => r.volt), luz = w.map(r => r.luz);
    return {
      volt_media: media(v), volt_std: desviacion(v),
      volt_min: Math.min(...v), volt_max: Math.max(...v),
      volt_pendiente: pendiente(v),
      volt_salto_max: Math.max(...v.slice(1).map((x, k) => Math.abs(x - v[k]))),
      luz_media: media(luz), luz_std: desviacion(luz), luz_pendiente: pendiente(luz),
      volt_por_luz: media(v) / media(luz),
      temp_ds18b20: media(w.map(r => r.tds)), temp_dht11: media(w.map(r => r.tdht)),
      humedad: media(w.map(r => r.hum))
    };
  }

  // Probabilidad de cada clase a partir de las variables de una ventana
  function probabilidades(modelo, x) {
    const fila = modelo.variables.map(n => Math.fround(x[n]));
    const margen = modelo.margen_base.slice();
    for (const t of modelo.arboles) {
      let n = 0;
      while (t.izq[n] !== -1) n = fila[t.var[n]] < Math.fround(t.val[n]) ? t.izq[n] : t.der[n];
      margen[t.clase] += t.val[n];
    }
    const max = Math.max(...margen);
    const e = margen.map(m => Math.exp(m - max));
    const suma = e.reduce((s, y) => s + y, 0);
    return e.map(y => y / suma);
  }

  // Devuelve {motivo} si no se puede clasificar, o {x, p} si se puede
  function evaluar(modelo, w) {
    const ok = (z) => typeof z === 'number' && isFinite(z) && z > -900;
    if (!w.every(r => ['volt', 'luz', 'tds', 'tdht', 'hum'].every(k => ok(r[k])))) return { motivo: 'sensor' };
    if (w.some(r => r.volt >= modelo.v_tope)) return { motivo: 'tope' };
    const x = caracteristicas(w);
    const [min, max] = modelo.rango_volt_media;
    if (x.volt_media < min || x.volt_media > max) return { motivo: 'rango' };
    return { x, p: probabilidades(modelo, x) };
  }

  const api = { caracteristicas, probabilidades, evaluar };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.ModeloSolar = api;
})(this);
