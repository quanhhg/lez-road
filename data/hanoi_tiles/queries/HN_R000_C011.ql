[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.525894,105.769224,20.571293,105.817423)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.525894,105.769224,20.571293,105.817423);
  node["barrier"](20.525894,105.769224,20.571293,105.817423);
);
(._; >>;);
out meta;
out count;
