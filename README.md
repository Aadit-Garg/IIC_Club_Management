# IIC Club Management

A comprehensive web application designed for managing the Innovation and Incubation Council (IIC) club activities, members, and resources.

## Features

- **User Authentication**: Secure login and role-based access control (JSec, Coordinator, Member).
- **Dashboard**: Overview of club statistics, recent activities, and upcoming events.
- **Member Management**: Directory of club members with their roles and contact information. Profile viewing and editing.
- **Event Calendar & Tracker**:
  - Schedule and track meetings and events.
  - Track attendance for events.
  - Collaborative MoM (Minutes of Meeting) writing.
- **Task Management**: Create, assign, and track tasks with status updates and due dates.
- **Discussion Channels**:
  - Group channels and direct messages.
  - Real-time chat interface.
  - Rich system messages (Cards) for new resources, events, and MoMs.
  - Features like polls, message reactions, task referencing, and @mentions.
- **Resource Hub**: Shared repository for links, documents, and other resources.
- **Collaborative Sheets**: Built-in spreadsheet functionality for collaborative data management.
- **Analytics Dashboard**: Insights into member productivity and engagement.
- **Notifications**: In-app notifications for important updates and mentions.

## Technologies Used

- **Backend**: Python, Flask, SQLAlchemy (SQLite/PostgreSQL)
- **Frontend**: HTML, CSS, JavaScript (Vanilla UI elements)
- **Deployment**: Configured for easily deployment (e.g., Pythonanywhere, Render)

## Setup and Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Aadit-Garg/IIC_Club_Management.git
   cd IIC_Club_Management
   ```

2. **Create a virtual environment (optional but recommended):**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Initialize the database:**
   ```bash
   python run.py  # Or run a script to initialize DB setup
   ```

5. **Run the application:**
   ```bash
   python app.py
   ```
   The application will be accessible at `http://localhost:5000`.

## Contributing
Contributions are welcome! Please open an issue or submit a pull request for any enhancements or bug fixes.
