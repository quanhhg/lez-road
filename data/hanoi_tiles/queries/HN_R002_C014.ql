[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.615505,105.913627,20.660943,105.961896)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.615505,105.913627,20.660943,105.961896);
  node["barrier"](20.615505,105.913627,20.660943,105.961896);
);
(._; >>;);
out meta;
out count;
