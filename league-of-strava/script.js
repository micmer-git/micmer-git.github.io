
  // Simulated Strava API JSON response
  const stravaData = {
    athlete: {
      id: 12345,
      username: 'johndoe',
      firstname: 'John',
      lastname: 'Doe',
      profile: 'https://via.placeholder.com/100',
    },
    activities: [
      // Activities for the week (sample data)
      { name: 'Morning Run', start_date: '2023-10-02', duration: 3600, distance: 10000, total_elevation_gain: 100, calories: 600 },
      { name: 'Evening Ride', start_date: '2023-10-03', duration: 5400, distance: 20000, total_elevation_gain: 200, calories: 800 },
      { name: 'Swim Session', start_date: '2023-10-04', duration: 1800, distance: 1000, total_elevation_gain: 0, calories: 300 },
      { name: 'Hiking', start_date: '2023-10-05', duration: 7200, distance: 15000, total_elevation_gain: 500, calories: 900 },
      { name: 'Yoga', start_date: '2023-10-06', duration: 3600, distance: 0, total_elevation_gain: 0, calories: 200 },
      { name: 'Cycling', start_date: '2023-10-07', duration: 5400, distance: 25000, total_elevation_gain: 300, calories: 700 },
      { name: 'Rest Day', start_date: '2023-10-08', duration: 0, distance: 0, total_elevation_gain: 0, calories: 0 },
    ],
    totals: {
      hours: 120, // Total hours of all time
      elevation: 50000, // Total elevation gain of all time
      calories: 70000, // Total calories burned of all time
      distance: 1000000, // Total distance in meters
      activities: 250, // Total number of activities
    },
  };

  // Rank System Configuration
  const rankConfig = [
    { name: 'Bronze 3', emoji: '🥉', minPoints: 0 },
    { name: 'Bronze 2', emoji: '🥉', minPoints: 50 },
    { name: 'Bronze 1', emoji: '🥉', minPoints: 100 },
    { name: 'Silver 3', emoji: '🥈', minPoints: 150 },
    { name: 'Silver 2', emoji: '🥈', minPoints: 200 },
    { name: 'Silver 1', emoji: '🥈', minPoints: 250 },
    { name: 'Gold 3', emoji: '🥇', minPoints: 300 },
    { name: 'Gold 2', emoji: '🥇', minPoints: 350 },
    { name: 'Gold 1', emoji: '🥇', minPoints: 400 },
    { name: 'Platinum 3', emoji: '🏆', minPoints: 450 },
    { name: 'Platinum 2', emoji: '🏆', minPoints: 500 },
    { name: 'Platinum 1', emoji: '🏆', minPoints: 550 },
    { name: 'Diamond 3', emoji: '💎', minPoints: 600 },
    { name: 'Diamond 2', emoji: '💎', minPoints: 650 },
    { name: 'Diamond 1', emoji: '💎', minPoints: 700 },
    { name: 'Master 3', emoji: '🔥', minPoints: 750 },
    { name: 'Master 2', emoji: '🔥', minPoints: 800 },
    { name: 'Master 1', emoji: '🔥', minPoints: 850 },
    { name: 'Grandmaster 3', emoji: '🚀', minPoints: 900 },
    { name: 'Grandmaster 2', emoji: '🚀', minPoints: 950 },
    { name: 'Grandmaster 1', emoji: '🚀', minPoints: 1000 },
    { name: 'Challenger', emoji: '🌟', minPoints: 1050 },
  ];

  // Function to calculate the user's rank based on total points
  function calculateRank(totalPoints) {
    let currentRank = rankConfig[0];
    let nextRank = rankConfig[1];

    for (let i = 0; i < rankConfig.length; i++) {
      if (totalPoints >= rankConfig[i].minPoints) {
        currentRank = rankConfig[i];
        nextRank = rankConfig[i + 1] || rankConfig[i]; // If at top rank
      } else {
        break;
      }
    }

    // Calculate progress percentage
    const pointsIntoCurrentRank = totalPoints - currentRank.minPoints;
    const pointsBetweenRanks = nextRank.minPoints - currentRank.minPoints;
    const progressPercent = (pointsIntoCurrentRank / pointsBetweenRanks) * 100;

    return {
      currentRank,
      nextRank,
      progressPercent,
      pointsIntoCurrentRank,
      pointsBetweenRanks,
    };
  }

  // Function to get lifetime stats icons and counts
  function getLifetimeStats(totals, weeklyTotals) {
    const stats = {};

    // Distance
    const totalDistanceIcons = Math.floor(totals.distance / 100000); // 100km per icon
    const weeklyDistanceIcons = Math.floor(weeklyTotals.distance / 100000);
    stats.distance = { icons: totalDistanceIcons, weekGain: weeklyDistanceIcons };

    // Elevation
    const totalElevationGems = Math.floor(totals.elevation / 1000); // 1000m per gem
    const weeklyElevationGems = Math.floor(weeklyTotals.elevation / 1000);
    stats.elevation = { icons: totalElevationGems, weekGain: weeklyElevationGems };

    // Calories (Pizzas)
    const totalPizzas = Math.floor(totals.calories / 1000); // 1000kcal per pizza
    const weeklyPizzas = Math.floor(weeklyTotals.calories / 1000);
    stats.calories = { icons: totalPizzas, weekGain: weeklyPizzas };

    return stats;
  }

  // Function to process and display data
  function displayData(data) {
    // Total points (you can define your own logic)
    const totalPoints = data.totals.hours; // For example, using total hours as points

    // Calculate rank
    const rankInfo = calculateRank(totalPoints);

    // Update Rank Section
    document.getElementById('current-rank').textContent = rankInfo.currentRank.name;
    document.getElementById('rank-emoji').textContent = rankInfo.currentRank.emoji;
    document.getElementById('progress-bar').style.width = `${rankInfo.progressPercent}%`;
    document.getElementById('current-rank-label').textContent = rankInfo.currentRank.name;
    document.getElementById('next-rank-label').textContent = rankInfo.nextRank.name;
    document.getElementById('current-points').textContent = totalPoints;
    document.getElementById('next-rank-points').textContent = rankInfo.nextRank.minPoints;

    // Populate Rank Tooltip
    const rankListElement = document.getElementById('rank-list');
    rankListElement.innerHTML = '';
    rankConfig.forEach(rank => {
      const li = document.createElement('li');
      li.textContent = `${rank.name} (${rank.minPoints} pts)`;
      rankListElement.appendChild(li);
    });

    // Weekly Totals
    const currentWeekActivities = data.activities.filter(activity => {
      const activityDate = new Date(activity.start_date);
      const today = new Date();
      const oneWeekAgo = new Date();
      oneWeekAgo.setDate(today.getDate() - 7);
      return activityDate >= oneWeekAgo && activityDate <= today;
    });

    const weeklyTotals = {
      hours: currentWeekActivities.reduce((sum, activity) => sum + activity.duration, 0) / 3600,
      distance: currentWeekActivities.reduce((sum, activity) => sum + activity.distance, 0),
      elevation: currentWeekActivities.reduce((sum, activity) => sum + activity.total_elevation_gain, 0),
      calories: currentWeekActivities.reduce((sum, activity) => sum + activity.calories, 0),
    };

    // Get Lifetime Stats
    const lifetimeStats = getLifetimeStats(data.totals, weeklyTotals);

    // Update Lifetime Stats Section
    document.getElementById('distance-value').textContent = lifetimeStats.distance.icons + ' 🚴‍♂️';
    document.getElementById('distance-week-gain').textContent = '+' + lifetimeStats.distance.weekGain + ' this week';

    document.getElementById('elevation-value').textContent = lifetimeStats.elevation.icons + ' 🏔️';
    document.getElementById('elevation-week-gain').textContent = '+' + lifetimeStats.elevation.weekGain + ' this week';

    document.getElementById('calories-value').textContent = lifetimeStats.calories.icons + ' 🍕';
    document.getElementById('calories-week-gain').textContent = '+' + lifetimeStats.calories.weekGain + ' this week';

    // Update Weekly Stats
    document.getElementById('weekly-hours').textContent = `${weeklyTotals.hours.toFixed(1)} hrs`;
    document.getElementById('weekly-distance').textContent = `${(weeklyTotals.distance / 1000).toFixed(1)} km`;
    document.getElementById('weekly-elevation').textContent = `${weeklyTotals.elevation} m`;
    document.getElementById('weekly-calories').textContent = `${weeklyTotals.calories} kcal`;
  }

  // Initialize
  displayData(stravaData);

  // Event Listener for Tooltip
  document.getElementById('progress-container').addEventListener('click', function() {
    const tooltip = document.getElementById('rank-tooltip');
    tooltip.style.display = tooltip.style.display === 'block' ? 'none' : 'block';
  });
