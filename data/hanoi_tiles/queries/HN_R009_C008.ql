[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.933103,105.627026,20.978465,105.675317)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.933103,105.627026,20.978465,105.675317);
  node["barrier"](20.933103,105.627026,20.978465,105.675317);
);
(._; >>;);
out meta;
out count;
