[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.933456,105.530853,20.978792,105.579117)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.933456,105.530853,20.978792,105.579117);
  node["barrier"](20.933456,105.530853,20.978792,105.579117);
);
(._; >>;);
out meta;
out count;
