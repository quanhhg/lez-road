[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.978789,105.482911,21.024112,105.531176)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.978789,105.482911,21.024112,105.531176);
  node["barrier"](20.978789,105.482911,21.024112,105.531176);
);
(._; >>;);
out meta;
out count;
