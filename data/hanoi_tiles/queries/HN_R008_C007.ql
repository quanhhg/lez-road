[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.888110,105.578767,20.933459,105.627029)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.888110,105.578767,20.933459,105.627029);
  node["barrier"](20.888110,105.578767,20.933459,105.627029);
);
(._; >>;);
out meta;
out count;
