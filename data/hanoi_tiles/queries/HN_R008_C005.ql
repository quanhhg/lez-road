[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.888435,105.482622,20.933758,105.530856)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.888435,105.482622,20.933758,105.530856);
  node["barrier"](20.888435,105.482622,20.933758,105.530856);
);
(._; >>;);
out meta;
out count;
