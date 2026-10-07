[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.931439,105.963612,20.976893,106.012000)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.931439,105.963612,20.976893,106.012000);
  node["barrier"](20.931439,105.963612,20.976893,106.012000);
);
(._; >>;);
out meta;
out count;
