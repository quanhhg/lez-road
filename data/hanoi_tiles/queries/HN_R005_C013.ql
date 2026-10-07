[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.751288,105.866413,20.796715,105.914713)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.751288,105.866413,20.796715,105.914713);
  node["barrier"](20.751288,105.866413,20.796715,105.914713);
);
(._; >>;);
out meta;
out count;
