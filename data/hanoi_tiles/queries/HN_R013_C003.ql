[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.114592,105.387058,21.159889,105.435338)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.114592,105.387058,21.159889,105.435338);
  node["barrier"](21.114592,105.387058,21.159889,105.435338);
);
(._; >>;);
out meta;
out count;
