[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.887730,105.674909,20.933106,105.723200)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.887730,105.674909,20.933106,105.723200);
  node["barrier"](20.887730,105.674909,20.933106,105.723200);
);
(._; >>;);
out meta;
out count;
