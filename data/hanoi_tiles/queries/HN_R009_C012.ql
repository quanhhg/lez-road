[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.932233,105.819365,20.977648,105.867712)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.932233,105.819365,20.977648,105.867712);
  node["barrier"](20.932233,105.819365,20.977648,105.867712);
);
(._; >>;);
out meta;
out count;
