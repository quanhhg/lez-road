[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.069142,105.483202,21.114465,105.531497)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.069142,105.483202,21.114465,105.531497);
  node["barrier"](21.069142,105.483202,21.114465,105.531497);
);
(._; >>;);
out meta;
out count;
