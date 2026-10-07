[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.707221,105.626092,20.752583,105.674309)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.707221,105.626092,20.752583,105.674309);
  node["barrier"](20.707221,105.626092,20.752583,105.674309);
);
(._; >>;);
out meta;
out count;
