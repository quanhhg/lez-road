[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.796712,105.818631,20.842125,105.866932)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.796712,105.818631,20.842125,105.866932);
  node["barrier"](20.796712,105.818631,20.842125,105.866932);
);
(._; >>;);
out meta;
out count;
