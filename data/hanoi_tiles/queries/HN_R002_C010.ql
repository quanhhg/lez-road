[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.616466,105.721693,20.661853,105.769907)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.616466,105.721693,20.661853,105.769907);
  node["barrier"](20.616466,105.721693,20.661853,105.769907);
);
(._; >>;);
out meta;
out count;
