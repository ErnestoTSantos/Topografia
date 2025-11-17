const map = L.map('map').setView([0,0], 2);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19
}).addTo(map);

let lastPlantId = null;
let lastLayer = null;

document.getElementById('btn-enviar').addEventListener('click', async () => {
  const fileInput = document.getElementById('input-dxf');
  if (!fileInput.files.length) {
    alert('Selecione um arquivo DXF');
    return;
  }

  const fd = new FormData();
  fd.append('arquivo_dxf', fileInput.files[0]);
  fd.append('nome', fileInput.files[0].name);

  const res = await fetch('/api/plant/', {
    method: 'POST',
    body: fd
  });

  if (!res.ok) {
    alert('Erro ao enviar arquivo');
    return;
  }

  const data = await res.json();
  lastPlantId = data.id;

  alert('Upload concluído! ID = ' + lastPlantId);

  await carregarEExibir(lastPlantId);
});

document.getElementById('btn-visualizar').addEventListener('click', async () => {
  if (!lastPlantId) {
    alert('Nenhuma planta enviada até agora');
    return;
  }
  await carregarEExibir(lastPlantId);
});

async function carregarEExibir(id) {
  const res = await fetch(`/api/plant/${id}/coordinates/`);
  if (!res.ok) {
    alert('Erro ao obter coordenadas');
    return;
  }

  const data = await res.json();
  const geojson = data.geojson;
  const metadata = data.metadata;

  if (lastLayer) map.removeLayer(lastLayer);

  lastLayer = L.geoJSON(geojson, {
    style: { weight: 2 },
    onEachFeature: (feature, layer) => {
      const a = feature?.properties?.area?.toFixed?.(3) ?? '-';
      const p = feature?.properties?.perimeter?.toFixed?.(3) ?? '-';
      layer.bindPopup(`Área: ${a} m²<br>Perímetro: ${p} m`);
    }
  }).addTo(map);

  map.fitBounds(lastLayer.getBounds());

  document.getElementById('info-metrics').textContent =
    `Área total: ${metadata.area.toFixed(3)} m² | Perímetro total: ${metadata.perimeter.toFixed(3)} m`;

  const rel = await fetch(`/api/plant/${id}/report/`);
  if (rel.ok) {
    const jr = await rel.json();
    const pdfUrl = jr.pdf;
    const linkPdf = document.getElementById('link-pdf');
    linkPdf.href = pdfUrl;
    linkPdf.style.display = 'inline';
  }
}
