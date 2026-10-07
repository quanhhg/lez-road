[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.159989,105.290853,21.205259,105.339120)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.159989,105.290853,21.205259,105.339120);
  node["barrier"](21.159989,105.290853,21.205259,105.339120);
);
(._; >>;);
out meta;
out count;
