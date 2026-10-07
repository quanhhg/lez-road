[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.571690,105.625538,20.617051,105.673711)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.571690,105.625538,20.617051,105.673711);
  node["barrier"](20.571690,105.625538,20.617051,105.673711);
);
(._; >>;);
out meta;
out count;
