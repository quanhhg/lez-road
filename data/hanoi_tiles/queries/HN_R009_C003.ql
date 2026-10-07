[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.933884,105.386591,20.979181,105.434813)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.933884,105.386591,20.979181,105.434813);
  node["barrier"](20.933884,105.386591,20.979181,105.434813);
);
(._; >>;);
out meta;
out count;
