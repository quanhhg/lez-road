[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.933612,105.482766,20.978935,105.531016)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.933612,105.482766,20.978935,105.531016);
  node["barrier"](20.933612,105.482766,20.978935,105.531016);
);
(._; >>;);
out meta;
out count;
