[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.796947,105.770590,20.842348,105.818878)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.796947,105.770590,20.842348,105.818878);
  node["barrier"](20.796947,105.770590,20.842348,105.818878);
);
(._; >>;);
out meta;
out count;
