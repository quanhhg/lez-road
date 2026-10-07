[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.841636,105.866929,20.887063,105.915260)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.841636,105.866929,20.887063,105.915260);
  node["barrier"](20.841636,105.866929,20.887063,105.915260);
);
(._; >>;);
out meta;
out count;
