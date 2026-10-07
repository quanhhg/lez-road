[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.887520,105.722980,20.932909,105.771284)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.887520,105.722980,20.932909,105.771284);
  node["barrier"](20.887520,105.722980,20.932909,105.771284);
);
(._; >>;);
out meta;
out count;
