[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.249989,105.435600,21.295299,105.483940)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.249989,105.435600,21.295299,105.483940);
  node["barrier"](21.249989,105.435600,21.295299,105.483940);
);
(._; >>;);
out meta;
out count;
