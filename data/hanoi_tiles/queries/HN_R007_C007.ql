[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.842933,105.578594,20.888282,105.626841)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.842933,105.578594,20.888282,105.626841);
  node["barrier"](20.842933,105.578594,20.888282,105.626841);
);
(._; >>;);
out meta;
out count;
