[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.661422,105.769904,20.706822,105.818148)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.661422,105.769904,20.706822,105.818148);
  node["barrier"](20.661422,105.769904,20.706822,105.818148);
);
(._; >>;);
out meta;
out count;
