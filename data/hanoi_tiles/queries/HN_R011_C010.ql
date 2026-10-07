[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.023044,105.723632,21.068433,105.771981)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.023044,105.723632,21.068433,105.771981);
  node["barrier"](21.023044,105.723632,21.068433,105.771981);
);
(._; >>;);
out meta;
out count;
