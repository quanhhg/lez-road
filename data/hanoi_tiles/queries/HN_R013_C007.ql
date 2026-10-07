[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.113988,105.579638,21.159338,105.627975)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.113988,105.579638,21.159338,105.627975);
  node["barrier"](21.113988,105.579638,21.159338,105.627975);
);
(._; >>;);
out meta;
out count;
