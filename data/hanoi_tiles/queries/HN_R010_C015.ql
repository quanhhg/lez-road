[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.976611,105.963902,21.022065,106.012305)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.976611,105.963902,21.022065,106.012305);
  node["barrier"](20.976611,105.963902,21.022065,106.012305);
);
(._; >>;);
out meta;
out count;
