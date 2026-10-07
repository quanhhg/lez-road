[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.977407,105.819611,21.022822,105.867973)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.977407,105.819611,21.022822,105.867973);
  node["barrier"](20.977407,105.819611,21.022822,105.867973);
);
(._; >>;);
out meta;
out count;
