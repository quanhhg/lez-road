[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.979280,105.290502,21.024550,105.338710)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.979280,105.290502,21.024550,105.338710);
  node["barrier"](20.979280,105.290502,21.024550,105.338710);
);
(._; >>;);
out meta;
out count;
