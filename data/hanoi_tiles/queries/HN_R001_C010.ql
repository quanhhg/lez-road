[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.571290,105.721480,20.616676,105.769680)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.571290,105.721480,20.616676,105.769680);
  node["barrier"](20.571290,105.721480,20.616676,105.769680);
);
(._; >>;);
out meta;
out count;
