[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.976890,105.915806,21.022331,105.964195)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.976890,105.915806,21.022331,105.964195);
  node["barrier"](20.976890,105.915806,21.022331,105.964195);
);
(._; >>;);
out meta;
out count;
