[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.933286,105.578940,20.978635,105.627217)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.933286,105.578940,20.978635,105.627217);
  node["barrier"](20.933286,105.578940,20.978635,105.627217);
);
(._; >>;);
out meta;
out count;
